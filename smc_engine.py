"""Audited SMC signal components merged from the uploaded XAU/USD bot.

This module contains strategy logic only: market structure, order blocks,
liquidity, FVG, candle patterns and RSI. Execution, Telegram delivery and
risk sizing remain outside this module.
"""
from __future__ import annotations

from typing import Any

MIN_FVG_SIZE = 1.50
EQUAL_LEVEL_TOL = 0.30
MIN_CONFIDENCE = 65


def find_swing_highs(candles: list[dict[str, Any]], lookback: int = 3) -> list[tuple[int, float]]:
    swings: list[tuple[int, float]] = []
    for i in range(lookback, len(candles) - lookback):
        if all(
            candles[i]["high"] >= candles[i - j]["high"]
            and candles[i]["high"] >= candles[i + j]["high"]
            for j in range(1, lookback + 1)
        ):
            swings.append((i, float(candles[i]["high"])))
    return swings


def find_swing_lows(candles: list[dict[str, Any]], lookback: int = 3) -> list[tuple[int, float]]:
    swings: list[tuple[int, float]] = []
    for i in range(lookback, len(candles) - lookback):
        if all(
            candles[i]["low"] <= candles[i - j]["low"]
            and candles[i]["low"] <= candles[i + j]["low"]
            for j in range(1, lookback + 1)
        ):
            swings.append((i, float(candles[i]["low"])))
    return swings


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    alpha = 2.0 / (period + 1.0)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1.0 - alpha) * result
    return result


def analyze_structure_bos(candles: list[dict[str, Any]]) -> tuple[str, str | None, bool]:
    if len(candles) < 20:
        return "NEUTRAL", None, False
    sample = candles[-60:]
    swing_highs = find_swing_highs(sample, lookback=3)
    swing_lows = find_swing_lows(sample, lookback=3)
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return "NEUTRAL", None, False

    curr_price = float(candles[-1]["close"])
    last_sh, prev_sh = swing_highs[-1][1], swing_highs[-2][1]
    last_sl, prev_sl = swing_lows[-1][1], swing_lows[-2][1]
    closes = [float(c["close"]) for c in candles]
    ema_fast = _ema(closes[-30:], 10)
    ema_slow = _ema(closes[-60:], 30)
    ema_bias = "BULLISH" if ema_fast > ema_slow else "BEARISH"

    bullish_bos = curr_price > last_sh
    bearish_bos = curr_price < last_sl
    was_bearish = last_sh < prev_sh and last_sl < prev_sl
    was_bullish = last_sh > prev_sh and last_sl > prev_sl
    bullish_choch = was_bearish and bullish_bos
    bearish_choch = was_bullish and bearish_bos

    if bullish_choch:
        return "BULLISH", "CHoCH", True
    if bearish_choch:
        return "BEARISH", "CHoCH", True
    if bullish_bos and ema_bias == "BULLISH" and last_sh > prev_sh:
        return "BULLISH", "BOS", False
    if bearish_bos and ema_bias == "BEARISH" and last_sl < prev_sl:
        return "BEARISH", "BOS", False
    if ema_bias == "BULLISH" and last_sh > prev_sh and last_sl > prev_sl:
        return "BULLISH", None, False
    if ema_bias == "BEARISH" and last_sh < prev_sh and last_sl < prev_sl:
        return "BEARISH", None, False
    return "NEUTRAL", None, False


def detect_order_block(candles: list[dict[str, Any]], bias: str) -> tuple[float | None, float | None, bool]:
    if len(candles) < 10:
        return None, None, False
    curr_price = float(candles[-1]["close"])
    start = max(len(candles) - 20, 3)
    for i in range(len(candles) - 3, start - 1, -1):
        c = candles[i]
        if bias == "BULLISH" and c["close"] < c["open"]:
            next_closes = [candles[i + j]["close"] for j in (1, 2)]
            if max(next_closes) > c["high"]:
                high, low = float(c["high"]), float(c["low"])
                return high, low, low <= curr_price <= high
        if bias == "BEARISH" and c["close"] > c["open"]:
            next_closes = [candles[i + j]["close"] for j in (1, 2)]
            if min(next_closes) < c["low"]:
                high, low = float(c["high"]), float(c["low"])
                return high, low, low <= curr_price <= high
    return None, None, False


def detect_liquidity_zones(candles: list[dict[str, Any]]) -> tuple[bool, bool, bool, bool]:
    if len(candles) < 10:
        return False, False, False, False
    recent = candles[-30:]
    reference_highs = [float(c["high"]) for c in recent[:-1]]
    reference_lows = [float(c["low"]) for c in recent[:-1]]
    last_high = float(candles[-1]["high"])
    last_low = float(candles[-1]["low"])

    high_levels = [h for i, h in enumerate(reference_highs) if any(abs(h - other) <= EQUAL_LEVEL_TOL for other in reference_highs[i + 1:])]
    low_levels = [l for i, l in enumerate(reference_lows) if any(abs(l - other) <= EQUAL_LEVEL_TOL for other in reference_lows[i + 1:])]
    equal_highs = bool(high_levels)
    equal_lows = bool(low_levels)
    swept_high = equal_highs and any(last_high > level for level in high_levels)
    swept_low = equal_lows and any(last_low < level for level in low_levels)
    return equal_highs, equal_lows, swept_high, swept_low


def detect_fvg(candles: list[dict[str, Any]]) -> tuple[str | None, int]:
    if len(candles) < 3:
        return None, 0
    last_index = len(candles) - 1
    for i in range(max(0, len(candles) - 12), len(candles) - 2):
        c1, c2, c3 = candles[i], candles[i + 1], candles[i + 2]
        if c1["high"] < c3["low"]:
            low, high = float(c1["high"]), float(c3["low"])
            if high - low >= MIN_FVG_SIZE:
                filled = any(float(c["low"]) <= high and float(c["high"]) >= low for c in candles[i + 3:last_index + 1])
                if not filled:
                    return "BULLISH_FVG", 1
        if c1["low"] > c3["high"]:
            low, high = float(c3["high"]), float(c1["low"])
            if high - low >= MIN_FVG_SIZE:
                filled = any(float(c["high"]) >= low and float(c["low"]) <= high for c in candles[i + 3:last_index + 1])
                if not filled:
                    return "BEARISH_FVG", 1
    return None, 0


def detect_liquidity_grab(candles: list[dict[str, Any]]) -> tuple[str | None, int]:
    if len(candles) < 10:
        return None, 0
    recent = candles[-10:]
    prev, curr = recent[-2], recent[-1]
    max_high = max(float(c["high"]) for c in recent[:-2])
    min_low = min(float(c["low"]) for c in recent[:-2])
    if float(prev["high"]) > max_high and float(prev["high"]) - max(float(prev["open"]), float(prev["close"])) >= 1.0 and curr["close"] < curr["open"]:
        return "BEARISH_GRAB", 2
    if float(prev["low"]) < min_low and min(float(prev["open"]), float(prev["close"])) - float(prev["low"]) >= 1.0 and curr["close"] > curr["open"]:
        return "BULLISH_GRAB", 2
    return None, 0


def check_candle_pattern(candles: list[dict[str, Any]]) -> tuple[str | None, int]:
    if len(candles) < 2:
        return None, 0
    c2, c3 = candles[-2], candles[-1]
    if c2["open"] < c2["close"] and c3["open"] > c3["close"] and c3["open"] >= c2["close"] and c3["close"] <= c2["open"]:
        return "BEARISH_ENGULF", 2
    if c2["open"] > c2["close"] and c3["open"] < c3["close"] and c3["open"] <= c2["close"] and c3["close"] >= c2["open"]:
        return "BULLISH_ENGULF", 2
    body = abs(float(c3["open"]) - float(c3["close"]))
    if body > 0 and float(c3["high"]) - max(float(c3["open"]), float(c3["close"])) > 2 * body:
        return "SHOOTING_STAR", 1
    if body > 0 and min(float(c3["open"]), float(c3["close"])) - float(c3["low"]) > 2 * body:
        return "HAMMER", 1
    return None, 0


def calculate_rsi(candles: list[dict[str, Any]], period: int = 14) -> float:
    if len(candles) < period + 1:
        return 50.0
    closes = [float(c["close"]) for c in candles[-(period + 1):]]
    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    return round(100 - (100 / (1 + avg_gain / avg_loss)), 2)


def generate_signal(candles_5m: list[dict[str, Any]], candles_15m: list[dict[str, Any]], min_confidence: int = MIN_CONFIDENCE) -> dict[str, Any] | None:
    if not candles_5m or not candles_15m:
        return None
    price = float(candles_5m[-1]["close"])
    tf_bias, bos_type, choch = analyze_structure_bos(candles_15m)
    if tf_bias == "NEUTRAL":
        return None

    m5_bias, m5_bos, _ = analyze_structure_bos(candles_5m)
    ob_high, ob_low, price_in_ob = detect_order_block(candles_5m, tf_bias)
    eq_highs, eq_lows, swept_high, swept_low = detect_liquidity_zones(candles_5m)
    liquidity, liq_score = detect_liquidity_grab(candles_5m)
    fvg, fvg_score = detect_fvg(candles_5m)
    pattern, pat_score = check_candle_pattern(candles_5m)
    rsi = calculate_rsi(candles_5m)

    long_score, short_score = 0, 0
    long_reasons: list[str] = []
    short_reasons: list[str] = []
    if tf_bias == "BULLISH":
        long_score += 30; long_reasons.append(f"15M Bullish ({bos_type or 'trend'}{' + CHoCH' if choch else ''})")
    else:
        short_score += 30; short_reasons.append(f"15M Bearish ({bos_type or 'trend'}{' + CHoCH' if choch else ''})")
    if choch and tf_bias == "BULLISH": long_score += 10; long_reasons.append("15M CHoCH Reversal")
    if choch and tf_bias == "BEARISH": short_score += 10; short_reasons.append("15M CHoCH Reversal")
    if m5_bias == "BULLISH": long_score += 15; long_reasons.append(f"M5 Bullish{' BOS' if m5_bos else ''}")
    if m5_bias == "BEARISH": short_score += 15; short_reasons.append(f"M5 Bearish{' BOS' if m5_bos else ''}")
    if price_in_ob and tf_bias == "BULLISH": long_score += 20; long_reasons.append("Price in Bullish Order Block")
    if price_in_ob and tf_bias == "BEARISH": short_score += 20; short_reasons.append("Price in Bearish Order Block")
    if swept_low and tf_bias == "BULLISH": long_score += 15; long_reasons.append("Equal Lows Swept")
    if swept_high and tf_bias == "BEARISH": short_score += 15; short_reasons.append("Equal Highs Swept")
    if liquidity == "BULLISH_GRAB": long_score += 10; long_reasons.append("Bullish Liquidity Grab")
    if liquidity == "BEARISH_GRAB": short_score += 10; short_reasons.append("Bearish Liquidity Grab")
    if fvg == "BULLISH_FVG": long_score += 10; long_reasons.append(f"Bullish FVG (≥${MIN_FVG_SIZE})")
    if fvg == "BEARISH_FVG": short_score += 10; short_reasons.append(f"Bearish FVG (≥${MIN_FVG_SIZE})")
    if pattern in ("BULLISH_ENGULF", "HAMMER"): long_score += pat_score * 5; long_reasons.append(f"Pattern: {pattern}")
    if pattern in ("BEARISH_ENGULF", "SHOOTING_STAR"): short_score += pat_score * 5; short_reasons.append(f"Pattern: {pattern}")
    if rsi < 35: long_score += 8; long_reasons.append(f"RSI Oversold ({rsi})")
    elif rsi > 65: short_score += 8; short_reasons.append(f"RSI Overbought ({rsi})")

    if long_score > short_score and long_score >= min_confidence and tf_bias == "BULLISH":
        signal, score, reasons = "BUY", min(long_score, 99), long_reasons
    elif short_score > long_score and short_score >= min_confidence and tf_bias == "BEARISH":
        signal, score, reasons = "SELL", min(short_score, 99), short_reasons
    else:
        signal, score, reasons = "HOLD", max(long_score, short_score), []

    return {
        "direction": signal,
        "confidence": score,
        "entry_low": round(price - 0.30, 2) if signal != "HOLD" else 0.0,
        "entry_high": round(price + 0.30, 2) if signal != "HOLD" else 0.0,
        "tp1": round(price + (1 if signal == "BUY" else -1) * 5.0, 2) if signal != "HOLD" else 0.0,
        "tp2": round(price + (1 if signal == "BUY" else -1) * 10.0, 2) if signal != "HOLD" else 0.0,
        "tp3": round(price + (1 if signal == "BUY" else -1) * 16.0, 2) if signal != "HOLD" else 0.0,
        "sl": round(price - 5.0, 2) if signal == "BUY" else round(price + 5.0, 2) if signal == "SELL" else 0.0,
        "reasons": reasons,
        "rsi": rsi,
        "tf_bias": tf_bias,
        "bos_type": bos_type or "None",
        "choch": choch,
        "ob_high": ob_high,
        "ob_low": ob_low,
        "price_in_ob": price_in_ob,
        "eq_highs": eq_highs,
        "eq_lows": eq_lows,
        "swept_high": swept_high,
        "swept_low": swept_low,
        "liquidity": liquidity or "None",
        "fvg": fvg or "None",
        "pattern": pattern or "None",
        "m5_bias": m5_bias,
        "scores": {"buy": long_score, "sell": short_score},
    }
