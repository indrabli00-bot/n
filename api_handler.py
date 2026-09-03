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
# Kept as a compatibility contract for callers/tests. Intraday candles are now
# persisted GoldAPI-derived samples rather than a second market-data provider.
CANDLE_CACHE_TTL = 10
_latest_smc_signal: dict[str, Any] | None = None


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
        return {"rsi": 50.0, "macd_hist": 0.0, "macd_signal": 0.0, "ema_trend": "Data Unavailable", "ema": None, "atr": 0.0, "bb_position": "Data Unavailable", "stoch_k": None}
    rsi = smc_engine.calculate_rsi(candles)
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    ema_trend = "Bullish Alignment" if ema20 > ema50 else "Bearish Alignment" if ema20 < ema50 else "Converging"
    ema12_series = []
    ema26_series = []
    e12 = e26 = closes[0]
    a12, a26 = 2 / 13, 2 / 27
    for value in closes:
        e12 = a12 * value + (1 - a12) * e12
        e26 = a26 * value + (1 - a26) * e26
        ema12_series.append(e12)
        ema26_series.append(e26)
    macd_series = [a - b for a, b in zip(ema12_series, ema26_series)]
    signal_line = _ema(macd_series, 9)
    macd_hist = macd_series[-1] - signal_line
    true_ranges = []
    for i in range(1, len(candles)):
        high = float(candles[i]["high"])
        low = float(candles[i]["low"])
        prev_close = float(candles[i - 1]["close"])
        true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    atr = sum(true_ranges[-14:]) / min(14, len(true_ranges)) if true_ranges else 0.0
    bb_window = closes[-20:]
    bb_mean = sum(bb_window) / len(bb_window)
    bb_variance = sum((value - bb_mean) ** 2 for value in bb_window) / len(bb_window)
    bb_std = bb_variance ** 0.5
    bb_upper = bb_mean + 2 * bb_std
    bb_lower = bb_mean - 2 * bb_std
    last_close = closes[-1]
    if bb_std == 0:
        bb_position = "Mid-Band"
    elif last_close >= bb_upper:
        bb_position = "Upper Band"
    elif last_close <= bb_lower:
        bb_position = "Lower Band"
    elif last_close > bb_mean:
        bb_position = "Upper Half"
    elif last_close < bb_mean:
        bb_position = "Lower Half"
    else:
        bb_position = "Mid-Band"
    stoch_window = candles[-14:]
    highest_high = max(float(c["high"]) for c in stoch_window)
    lowest_low = min(float(c["low"]) for c in stoch_window)
    stoch_k = 50.0 if highest_high == lowest_low else ((last_close - lowest_low) / (highest_high - lowest_low)) * 100
    return {"rsi": rsi, "macd_hist": round(macd_hist, 2), "macd_signal": round(signal_line, 2), "ema_trend": ema_trend, "ema": round(ema20, 2), "atr": round(atr, 2), "bb_position": bb_position, "stoch_k": round(stoch_k, 2)}


async def get_smc_signal(reference_price: float | None = None) -> dict[str, Any] | None:
    # SMC needs 60 contiguous 5M bars and 20 contiguous 15M bars. Both series
    # are built from real GoldAPI samples; if either series is not warmed up,
    # fail closed instead of inventing history.
    import asyncio
    candles_5m, candles_15m = await asyncio.gather(fetch_candles("5min", 60), fetch_candles("15min", 20))
    if not candles_5m or not candles_15m:
        return {"direction": "HOLD", "confidence": 0, "entry_low": 0.0, "entry_high": 0.0, "tp1": 0.0, "tp2": 0.0, "tp3": 0.0, "sl": 0.0, "reasons": ["LIVE 5M/15M CANDLE DATA UNAVAILABLE", "WAIT FOR LIVE DATA BEFORE ENTRY"], "tf_bias": "DATA_GAP", "signal_price": reference_price or 0.0, "signal_price_source": "LIVE_REFERENCE" if reference_price is not None else "NONE"}
    return smc_engine.generate_signal(candles_5m, candles_15m, reference_price=reference_price)


def get_technical_indicators(price: float, change_pct: float) -> dict[str, Any]:
    """Return technical indicators from persisted live GoldAPI-derived bars."""
    candles_5m = market_candles.get_candles("5min", 60) or []
    candles_15m = market_candles.get_candles("15min", 20) or []
    technical = _technical_indicators(candles_5m)
    if candles_5m and candles_15m:
        sig = smc_engine.generate_signal(candles_5m, candles_15m, reference_price=float(price))
    else:
        sig = {"direction": "HOLD", "confidence": 0, "entry_low": 0.0, "entry_high": 0.0, "tp1": 0.0, "tp2": 0.0, "tp3": 0.0, "sl": 0.0, "reasons": ["LIVE SMC DATA UNAVAILABLE", "WAIT FOR LIVE DATA BEFORE ENTRY"], "tf_bias": "DATA_GAP", "signal_price": price, "signal_price_source": "LIVE_REFERENCE"}
    technical["smc_signal"] = sig
    return technical


def _determine_signal(price: float, indicators: dict[str, Any]) -> dict[str, Any]:
    smc_signal = indicators.get("smc_signal")
    if smc_signal is not None:
        return smc_signal
    return {"direction": "HOLD", "confidence": 0, "entry_low": 0.0, "entry_high": 0.0, "tp1": 0.0, "tp2": 0.0, "tp3": 0.0, "sl": 0.0, "reasons": ["LIVE SMC DATA UNAVAILABLE", "WAIT FOR LIVE DATA BEFORE ENTRY"], "tf_bias": "DATA_GAP", "signal_price": price, "signal_price_source": "LIVE_REFERENCE"}
