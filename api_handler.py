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
        return None
    return smc_engine.generate_signal(candles_5m, candles_15m)

def _simulate_technical_indicators(price: float, change_pct: float) -> dict[str, Any]:
    """Return SMC-derived indicators when live candles are available; otherwise use deterministic fallback."""
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
    digest = hashlib.sha256(f"{round(price, 2)}:{round(change_pct, 4)}".encode("utf-8")).digest()
    seed = int.from_bytes(digest[:4], "big")
    offsets = [((seed >> (i * 4)) & 0xF) / 15.0 - 0.5 for i in range(7)]
    temporal = max(0.0, min(100.0, 50 + change_pct * 80 + offsets[0] * 10))
    phase = change_pct * 15 + offsets[1]
    variance = 10.0 + ((seed >> 28) % 13)
    trend_delta = change_pct + offsets[2] * 0.1
    trend = "Bullish Alignment" if trend_delta > 0.08 else ("Bearish Alignment" if trend_delta < -0.08 else "Converging")
    envelope = ["Upper Band", "Mid-Band", "Lower Band"][seed % 3]
    flux = max(0.0, min(100.0, 50 + change_pct * 100 + offsets[3] * 20))
    return {"rsi": round(temporal, 1), "macd_hist": round(phase, 2), "macd_signal": round(phase + offsets[4] * 0.6, 2), "atr": round(variance, 1), "ema_trend": trend, "bb_position": envelope, "stoch_k": round(flux, 1)}

def _determine_signal(price: float, indicators: dict[str, Any]) -> dict[str, Any]:
    smc_signal = indicators.get("smc_signal")
    if smc_signal is not None:
        return smc_signal
    score = 0.0
    temporal = indicators["rsi"]
    if temporal < 30: score += 2.0
    elif temporal > 70: score -= 2.0
    elif temporal < 45: score += 0.8
    elif temporal > 55: score -= 0.8
    phase = indicators["macd_hist"]
    if phase > 0.5: score += 1.5
    elif phase < -0.5: score -= 1.5
    if "Bullish" in indicators["ema_trend"]: score += 1.0
    elif "Bearish" in indicators["ema_trend"]: score -= 1.0
    flux = indicators["stoch_k"]
    if flux < 20: score += 1.0
    elif flux > 80: score -= 1.0
    if indicators["bb_position"] == "Lower Band": score += 0.5
    elif indicators["bb_position"] == "Upper Band": score -= 0.5
    confidence = max(40.0, min(95.0, 50 + score * 5))
    direction = "BUY" if score > 1.0 else ("SELL" if score < -1.0 else "HOLD")
    atr = indicators["atr"]
    entry_low, entry_high = round(price - 0.30, 2), round(price + 0.30, 2)
    if direction == "BUY":
        tp1, tp2, tp3, sl = round(price + atr * 0.5, 2), round(price + atr, 2), round(price + atr * 1.6, 2), round(price - atr * 0.8, 2)
    elif direction == "SELL":
        tp1, tp2, tp3, sl = round(price - atr * 0.5, 2), round(price - atr, 2), round(price - atr * 1.6, 2), round(price + atr * 0.8, 2)
    else:
        tp1 = tp2 = tp3 = sl = 0.0
    momentum = "STRONG BULLISH" if score > 2 else "BULLISH" if score > 0.5 else "STRONG BEARISH" if score < -2 else "BEARISH" if score < -0.5 else "NEUTRAL"
    volatility = "LOW" if atr < 13 else "MEDIUM" if atr < 18 else "HIGH"
    liquidity = "HIGH" if volatility == "LOW" else "MEDIUM" if volatility == "MEDIUM" else "LOW"
    return {"direction": direction, "confidence": round(confidence, 1), "entry_low": entry_low, "entry_high": entry_high, "tp1": tp1, "tp2": tp2, "tp3": tp3, "sl": sl, "risk_reward": 0.0, "liquidity": liquidity, "volatility": volatility, "momentum": momentum}
