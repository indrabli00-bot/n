"""XAU/USD price feed — multi-source cascade with circuit breaker (Phase 0.2).

Sumber (urutan):
  1. GoldAPI.io      (primary, butuh GOLDAPI_API_KEY)
  2. gold-api.com    (cadangan, tanpa key — mid price, bid=ask)
  3. goldprice.org   (cadangan, tanpa key — mid + change + prev close)

Aturan kejujuran (Phase 0.2):
  - TIDAK ada harga fabrikasi/sintetis.
  - Jika semua sumber live gagal: harga terakhir yang PERNAH valid
    dikembalikan dengan flag `stale: True` (maks 30 menit) — diberi label
    STALE yang jelas di UI, bukan dijadikan harga hidup.
  - Jika tidak ada cache sama sekali: caller menampilkan DATA GAP.

Circuit breaker per sumber: 3 kegagalan beruntun -> sumber didinginkan
(COOLDOWN_SECONDS) agar cascade tidak menghabiskan rate-limit sia-sia.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

import aiohttp

logger = logging.getLogger(__name__)

FAST_TIMEOUT = aiohttp.ClientTimeout(total=8)
COOLDOWN_SECONDS = 120
FAILURE_THRESHOLD = 3
STALE_MAX_SECONDS = 30 * 60  # harga cache dianggap stale maksimal 30 menit


class SourceUnavailable(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Sumber 1 — GoldAPI.io (primary)
# ---------------------------------------------------------------------------
async def fetch_goldapi() -> dict[str, Any]:
    api_key = os.getenv("GOLDAPI_API_KEY", "").strip()
    if not api_key:
        raise SourceUnavailable("GoldAPI: no API key configured")

    url = "https://www.goldapi.io/api/price/XAU/USD"
    headers = {"x-access-token": api_key, "Content-Type": "application/json"}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=FAST_TIMEOUT) as resp:
            if resp.status == 429:
                raise SourceUnavailable("GoldAPI: rate limit reached")
            if resp.status in (401, 403):
                raise SourceUnavailable("GoldAPI: authentication failed")
            resp.raise_for_status()
            data = await resp.json()

    price = data.get("price")
    bid = data.get("bid")
    ask = data.get("ask")
    if not isinstance(price, (int, float)) or price <= 0:
        raise SourceUnavailable("GoldAPI: invalid price")
    if not isinstance(bid, (int, float)) or bid <= 0:
        raise SourceUnavailable("GoldAPI: invalid bid")
    if not isinstance(ask, (int, float)) or ask <= 0:
        raise SourceUnavailable("GoldAPI: invalid ask")

    ts = data.get("datetime") or datetime.now(timezone.utc).isoformat()
    return {
        "source": "GOLD_API",
        "symbol": "XAU/USD",
        "bid": float(bid),
        "ask": float(ask),
        "close": float(price),
        "high": float(data.get("high_price", price)),
        "low": float(data.get("low_price", price)),
        "change": float(data.get("ch", data.get("change", 0.0)) or 0.0),
        "change_percent": float(data.get("chp", data.get("change_percent", 0.0)) or 0.0),
        "volume": "N/A",
        "timestamp": str(ts),
        "exchange": data.get("exchange", "FOREX"),
    }


# ---------------------------------------------------------------------------
# Sumber 2 — gold-api.com (keyless, mid price)
# ---------------------------------------------------------------------------
async def fetch_goldapi_com() -> dict[str, Any]:
    url = "https://api.gold-api.com/price/XAU"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=FAST_TIMEOUT) as resp:
            if resp.status == 429:
                raise SourceUnavailable("gold-api.com: rate limit reached")
            resp.raise_for_status()
            data = await resp.json()

    price = data.get("price")
    if not isinstance(price, (int, float)) or price <= 0:
        raise SourceUnavailable("gold-api.com: invalid price")
    price = float(price)
    # Jujur: sumber ini hanya memberi mid — bid = ask = mid (tanpa spread rekaan).
    return {
        "source": "GOLD_API_COM",
        "symbol": "XAU/USD",
        "bid": price,
        "ask": price,
        "close": price,
        "high": price,
        "low": price,
        "change": 0.0,
        "change_percent": 0.0,
        "volume": "N/A",
        "timestamp": str(data.get("updatedAt") or datetime.now(timezone.utc).isoformat()),
    }


# ---------------------------------------------------------------------------
# Sumber 3 — goldprice.org (keyless, mid + change)
# ---------------------------------------------------------------------------
async def fetch_goldprice_org() -> dict[str, Any]:
    url = "https://data-asg.goldprice.org/dbXRates/USD"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; NeuralGold/3.2)"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=FAST_TIMEOUT) as resp:
            if resp.status == 429:
                raise SourceUnavailable("goldprice.org: rate limit reached")
            resp.raise_for_status()
            data = await resp.json()

    items = data.get("items") or []
    if not items:
        raise SourceUnavailable("goldprice.org: empty payload")
    item = items[0]
    price = item.get("xauPrice")
    if not isinstance(price, (int, float)) or price <= 0:
        raise SourceUnavailable("goldprice.org: invalid price")
    price = float(price)
    chg = float(item.get("chgXau", 0.0) or 0.0)
    prev_close = float(item.get("xauClose", price) or price)
    change_pct = (chg / prev_close * 100.0) if prev_close else 0.0
    ts = data.get("ts") or datetime.now(timezone.utc).timestamp() * 1000
    iso = datetime.fromtimestamp(float(ts) / 1000.0, tz=timezone.utc).isoformat()
    return {
        "source": "GOLDPRICE_ORG",
        "symbol": "XAU/USD",
        "bid": price,
        "ask": price,
        "close": price,
        "high": price,
        "low": price,
        "change": chg,
        "change_percent": round(change_pct, 2),
        "volume": "N/A",
        "timestamp": iso,
    }


# ---------------------------------------------------------------------------
# Cascade + circuit breaker + stale cache
# ---------------------------------------------------------------------------
_SOURCES: list[tuple[str, Callable[[], Awaitable[dict[str, Any]]]]] = [
    ("GOLD_API", fetch_goldapi),
    ("GOLD_API_COM", fetch_goldapi_com),
    ("GOLDPRICE_ORG", fetch_goldprice_org),
]

_breaker: dict[str, dict[str, float]] = {}   # name -> {"fails": int, "cooldown_until": epoch}
_last_good: dict[str, Any] | None = None     # harga valid terakhir (untuk stale jujur)
_last_good_ts: datetime | None = None


def _breaker_open(name: str) -> bool:
    state = _breaker.get(name)
    if not state:
        return False
    if state["fails"] < FAILURE_THRESHOLD:
        return False
    if time.time() >= state["cooldown_until"]:
        return False
    return True


def _record_success(name: str) -> None:
    _breaker[name] = {"fails": 0, "cooldown_until": 0.0}


def _record_failure(name: str) -> None:
    state = _breaker.setdefault(name, {"fails": 0, "cooldown_until": 0.0})
    state["fails"] += 1
    if state["fails"] >= FAILURE_THRESHOLD:
        state["cooldown_until"] = time.time() + COOLDOWN_SECONDS
        logger.warning("Circuit breaker OPEN for %s (cooldown %ds)", name, COOLDOWN_SECONDS)


def _remember_last_good(price: dict[str, Any]) -> None:
    global _last_good, _last_good_ts
    _last_good = dict(price)
    _last_good_ts = _now()


def _stale_copy() -> dict[str, Any] | None:
    if not _last_good or not _last_good_ts:
        return None
    age = (_now() - _last_good_ts).total_seconds()
    if age > STALE_MAX_SECONDS:
        return None
    stale = dict(_last_good)
    stale["source"] = f"CACHE (STALE {int(age // 60)}m)"
    stale["stale"] = True
    stale["bid"] = float(stale["bid"])
    stale["ask"] = float(stale["ask"])
    return stale


async def fetch_price_cascade() -> dict[str, Any]:
    """Coba sumber berurutan (skip yang breaker-nya open). Semua gagal -> stale cache jujur -> raise."""
    errors: list[str] = []
    for name, fetcher in _SOURCES:
        if _breaker_open(name):
            errors.append(f"{name}: circuit open (cooldown)")
            continue
        try:
            price = await fetcher()
            _record_success(name)
            _remember_last_good(price)
            return price
        except Exception as exc:
            _record_failure(name)
            errors.append(f"{name}: {exc}")
            logger.warning("Price source %s failed: %s", name, exc)

    stale = _stale_copy()
    if stale is not None:
        logger.warning("All live sources failed; serving STALE cache (%s).", stale.get("source"))
        return stale

    raise RuntimeError("LIVE FEED UNAVAILABLE — " + " | ".join(errors))
