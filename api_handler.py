"""Market data and Neural Signal engine for NEURAL GOLD v3.2."""
from __future__ import annotations

import asyncio
import hashlib
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

def _simulate_technical_indicators(price: float, change_pct: float) -> dict[str, Any]:
    """Return live SMC-derived indicators; never fabricate a trading signal when SMC data is unavailable."""
    if _latest_smc_signal is not None:
        sig = _latest_smc_signal
        return {
            "rsi": sig.get("rsi", 50.0),
            "macd_hist": 0.0,
            "macd_signal": 0.0,
            "atr": abs(float(sig.get("tp2", price)) - price) / 1.0,
            "ema_trend": "Bullish Alignment" if sig.get("tf_bias") == "BULLISH" else "Bearish Alignment" if sig.get("tf_bias") == "BEARISH" else "Converging",
            "bb_position": "Mid-Band",
            "stoch_k": 50.0,
            "smc_signal": sig,
        }
    return {
        "rsi": 50.0, "macd_hist": 0.0, "macd_signal": 0.0, "atr": 0.0,
        "ema_trend": "Data Unavailable", "bb_position": "Unavailable", "stoch_k": 50.0,
        "smc_signal": {"direction":"HOLD","confidence":0,"entry_low":0.0,"entry_high":0.0,"tp1":0.0,"tp2":0.0,"tp3":0.0,"sl":0.0,"reasons":["LIVE SMC DATA UNAVAILABLE","WAIT FOR LIVE DATA BEFORE ENTRY"],"tf_bias":"DATA_GAP"},
    }

def _determine_signal(price: float, indicators: dict[str, Any]) -> dict[str, Any]:
    smc_signal = indicators.get("smc_signal")
    if smc_signal is not None:
        return smc_signal
    return {"direction":"HOLD","confidence":0,"entry_low":0.0,"entry_high":0.0,"tp1":0.0,"tp2":0.0,"tp3":0.0,"sl":0.0,"reasons":["LIVE SMC DATA UNAVAILABLE","WAIT FOR LIVE DATA BEFORE ENTRY"],"tf_bias":"DATA_GAP"}
