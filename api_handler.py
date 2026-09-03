"""Market data and Neural Signal engine for NEURAL GOLD v3.2."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

import aiohttp

import database
import price_sources
import smc_engine

logger = logging.getLogger(__name__)
SESSION_CACHE_TTL = 30
CANDLE_CACHE_TTL = 240
_candle_cache: dict[str, tuple[datetime, list[dict[str, Any]]]] = {}
_latest_smc_signal: dict[str, Any] | None = None

async def fetch_xauusd_price() -> dict[str, Any]:
    return await price_sources.fetch_price_cascade()

async def get_cached_or_fresh_price(user_id: int) -> dict[str, Any]:
    global _latest_smc_signal
    try:
        sess = database.get_or_create_session(user_id)
    except Exception as exc:
        logger.warning("Session lookup failed: %s", exc)
        return await fetch_xauusd_price()

    if sess.last_fetch_time:
        last_fetch = database.normalize_datetime_utc(sess.last_fetch_time)
        age = (datetime.now(timezone.utc) - last_fetch).total_seconds() if last_fetch else float("inf")
        if age < SESSION_CACHE_TTL and sess.last_price_bid is not None and sess.last_price_ask is not None:
            price = {
                "source": "SESSION_CACHE", "symbol": "XAU/USD",
                "bid": float(sess.last_price_bid), "ask": float(sess.last_price_ask),
                "close": (float(sess.last_price_bid) + float(sess.last_price_ask)) / 2,
                "high": float(sess.last_price_high or sess.last_price_ask),
                "low": float(sess.last_price_low or sess.last_price_bid),
                "change": 0.0, "change_percent": 0.0, "volume": "N/A",
                "timestamp": last_fetch.isoformat(),
            }
            _latest_smc_signal = await get_smc_signal()
            return price

    price_data = await fetch_xauusd_price()
    try:
        database.update_session(
            user_id, last_price_bid=price_data["bid"], last_price_ask=price_data["ask"],
            last_price_high=price_data["high"], last_price_low=price_data["low"],
            last_fetch_time=datetime.now(timezone.utc),
        )
    except Exception as exc:
        logger.warning("Failed to persist price cache: %s", exc)
    _latest_smc_signal = await get_smc_signal()
    return price_data

async def fetch_candles(interval: str, outputsize: int = 100) -> list[dict[str, Any]] | None:
    """Fetch XAU/USD candles from TwelveData for the merged SMC engine."""
    api_key = os.getenv("TWELVEDATA_API_KEY", "").strip()
    if not api_key:
        return None
    key = f"{interval}:{outputsize}"
    now = datetime.now(timezone.utc)
    cached = _candle_cache.get(key)
    if cached and (now - cached[0]).total_seconds() < CANDLE_CACHE_TTL:
        return cached[1]
    params = {"symbol": "XAU/USD", "interval": interval, "outputsize": outputsize, "apikey": api_key, "format": "JSON"}
    try:
        timeout = aiohttp.ClientTimeout(total=12)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://api.twelvedata.com/time_series", params=params) as response:
                response.raise_for_status()
                data = await response.json()
        if "values" not in data:
            logger.warning("TwelveData candle error: %s", data.get("message") or data)
            return None
        candles = [{
            "time": str(c["datetime"]), "open": float(c["open"]), "high": float(c["high"]),
            "low": float(c["low"]), "close": float(c["close"])
        } for c in reversed(data["values"])]
        if len(candles) < 20:
            return None
        _candle_cache[key] = (now, candles)
        return candles
    except Exception as exc:
        logger.warning("TwelveData %s candle fetch failed: %s", interval, exc)
        return None

async def get_smc_signal() -> dict[str, Any] | None:
    candles_5m, candles_15m = await asyncio.gather(fetch_candles("5min", 100), fetch_candles("15min", 100))
    if not candles_5m or not candles_15m:
        return {"direction":"HOLD","confidence":0,"entry_low":0.0,"entry_high":0.0,"tp1":0.0,"tp2":0.0,"tp3":0.0,"sl":0.0,"reasons":["LIVE 5M/15M CANDLE DATA UNAVAILABLE","WAIT FOR LIVE DATA BEFORE ENTRY"],"tf_bias":"DATA_GAP"}
    return smc_engine.generate_signal(candles_5m, candles_15m)

def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    alpha = 2 / (period + 1)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1 - alpha) * result
    return result

def _technical_indicators(candles: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate Structure Map indicators directly from the live 5-minute candle series."""
    closes = [float(c["close"]) for c in candles]
    if len(closes) < 35:
        return {"rsi": 50.0, "macd_hist": 0.0, "macd_signal": 0.0, "ema_trend": "Data Unavailable", "ema": None, "atr": 0.0}

    rsi = smc_engine.calculate_rsi(candles)
    ema20 = _ema(closes[-60:], 20)
    ema50 = _ema(closes[-60:], 50)
    ema_trend = "Bullish Alignment" if ema20 > ema50 else "Bearish Alignment" if ema20 < ema50 else "Converging"

    macd_series = []
    for i in range(26, len(closes)):
        series = closes[:i + 1]
        macd_series.append(_ema(series[-60:], 12) - _ema(series[-60:], 26))
    macd_line = macd_series[-1] if macd_series else 0.0
    macd_signal = _ema(macd_series[-9:], 9) if macd_series else 0.0
    macd_hist = macd_line - macd_signal

    true_ranges = []
    for i in range(1, len(candles)):
        high = float(candles[i]["high"])
        low = float(candles[i]["low"])
        prev_close = float(candles[i - 1]["close"])
        true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    atr = sum(true_ranges[-14:]) / min(14, len(true_ranges)) if true_ranges else 0.0

    return {
        "rsi": rsi,
        "macd_hist": round(macd_hist, 2),
        "macd_signal": round(macd_signal, 2),
        "ema_trend": ema_trend,
        "ema": round(ema20, 2),
        "atr": round(atr, 2),
        "bb_position": "Mid-Band",
        "stoch_k": 50.0,
    }

def _simulate_technical_indicators(price: float, change_pct: float) -> dict[str, Any]:
    """Compatibility wrapper: return live candle indicators plus the current SMC signal."""
    candles = _candle_cache.get("5min:100", (None, []))[1]
    technical = _technical_indicators(candles)
    sig = _latest_smc_signal or {"direction":"HOLD","confidence":0,"entry_low":0.0,"entry_high":0.0,"tp1":0.0,"tp2":0.0,"tp3":0.0,"sl":0.0,"reasons":["LIVE SMC DATA UNAVAILABLE","WAIT FOR LIVE DATA BEFORE ENTRY"],"tf_bias":"DATA_GAP"}
    technical["smc_signal"] = sig
    return technical

def _determine_signal(price: float, indicators: dict[str, Any]) -> dict[str, Any]:
    smc_signal = indicators.get("smc_signal")
    if smc_signal is not None:
        return smc_signal
    return {"direction":"HOLD","confidence":0,"entry_low":0.0,"entry_high":0.0,"tp1":0.0,"tp2":0.0,"tp3":0.0,"sl":0.0,"reasons":["LIVE SMC DATA UNAVAILABLE","WAIT FOR LIVE DATA BEFORE ENTRY"],"tf_bias":"DATA_GAP"}
