"""Market data and Neural Signal engine for NEURAL GOLD v3.2."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import database
import market_candles
import price_sources
import smc_engine

logger = logging.getLogger(__name__)
SESSION_CACHE_TTL = 10
CANDLE_CACHE_TTL = 10
_latest_smc_signal: dict[str, Any] | None = None


def _data_gap_signal(reference_price: float | None = None) -> dict[str, Any]:
    return {
        "direction": "HOLD",
        "confidence": 0,
        "entry_low": 0.0,
        "entry_high": 0.0,
        "tp1": 0.0,
        "tp2": 0.0,
        "tp3": 0.0,
        "sl": 0.0,
        "reasons": ["LIVE 5M/15M CANDLE DATA UNAVAILABLE", "WAIT FOR LIVE DATA BEFORE ENTRY"],
        "tf_bias": "DATA_GAP",
        "signal_price": float(reference_price or 0.0),
        "signal_price_source": "LIVE_REFERENCE" if reference_price is not None else "NONE",
    }


async def fetch_xauusd_price() -> dict[str, Any]:
    return await price_sources.fetch_price_cascade()


async def get_cached_or_fresh_price(user_id: int) -> dict[str, Any]:
    global _latest_smc_signal
    try:
        sess = database.get_or_create_session(user_id)
    except Exception as exc:
        logger.warning("Session lookup failed: %s", exc)
        price = await fetch_xauusd_price()
        _latest_smc_signal = await get_smc_signal(reference_price=float(price["bid"]))
        return price

    if sess.last_fetch_time:
        last_fetch = database.normalize_datetime_utc(sess.last_fetch_time)
        age = (datetime.now(timezone.utc) - last_fetch).total_seconds() if last_fetch else float("inf")
        if age < SESSION_CACHE_TTL and sess.last_price_bid is not None and sess.last_price_ask is not None:
            price = {
                "source": "SESSION_CACHE",
                "symbol": "XAU/USD",
                "bid": float(sess.last_price_bid),
                "ask": float(sess.last_price_ask),
                "close": (float(sess.last_price_bid) + float(sess.last_price_ask)) / 2,
                "high": float(sess.last_price_high or sess.last_price_ask),
                "low": float(sess.last_price_low or sess.last_price_bid),
                "change": 0.0,
                "change_percent": 0.0,
                "volume": "N/A",
                "timestamp": last_fetch.isoformat(),
            }
            _latest_smc_signal = await get_smc_signal(reference_price=float(price["bid"]))
            return price

    price_data = await fetch_xauusd_price()
    try:
        database.update_session(
            user_id,
            last_price_bid=price_data["bid"],
            last_price_ask=price_data["ask"],
            last_price_high=price_data["high"],
            last_price_low=price_data["low"],
            last_fetch_time=datetime.now(timezone.utc),
        )
    except Exception as exc:
        logger.warning("Failed to persist price cache: %s", exc)
    _latest_smc_signal = await get_smc_signal(reference_price=float(price_data["bid"]))
    return price_data


async def fetch_candles(interval: str, outputsize: int = 100) -> list[dict[str, Any]] | None:
    """Return M5/M15 bars built only from persisted live GoldAPI samples."""
    return market_candles.get_candles(interval, outputsize)


async def get_smc_signal(reference_price: float | None = None) -> dict[str, Any]:
    """Generate the only canonical customer signal from persisted live candles."""
    import asyncio

    candles_5m, candles_15m = await asyncio.gather(
        fetch_candles("5min", 60),
        fetch_candles("15min", 20),
    )
    if not candles_5m or not candles_15m:
        return _data_gap_signal(reference_price)
    return smc_engine.generate_signal(candles_5m, candles_15m, reference_price=reference_price)


def get_latest_smc_signal() -> dict[str, Any] | None:
    """Return the latest signal already computed during the price refresh."""
    return _latest_smc_signal


def _technical_indicators(candles: list[dict[str, Any]]) -> dict[str, Any]:
    """Backward-compatible indicator helper retained for the existing test contract."""
    return smc_engine.get_technical_indicators(candles)


def get_technical_indicators(price: float, change_pct: float) -> dict[str, Any]:
    """Return Structure Map indicators from the same persisted live candle engine."""
    candles_5m = market_candles.get_candles("5min", 60) or []
    candles_15m = market_candles.get_candles("15min", 20) or []
    if not candles_5m or not candles_15m:
        technical = {"rsi": None, "macd_hist": None, "macd_signal": None, "ema_trend": "Data Unavailable", "ema": None, "atr": None, "bb_position": "Data Unavailable", "stoch_k": None}
        technical["smc_signal"] = _data_gap_signal(price)
        return technical

    technical = smc_engine.get_technical_indicators(candles_5m)
    technical["smc_signal"] = smc_engine.generate_signal(candles_5m, candles_15m, reference_price=float(price))
    return technical


def _determine_signal(price: float, indicators: dict[str, Any]) -> dict[str, Any]:
    return indicators.get("smc_signal") or _data_gap_signal(price)
