from __future__ import annotations

from statistics import mean
from config import MIN_MARKET_SAMPLES


def ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    value = mean(values[:period])
    for value_now in values[period:]:
        value = value_now * k + value * (1 - k)
    return value


def atr(values: list[float], period: int = 14) -> float | None:
    if len(values) < period + 1:
        return None
    return mean(abs(values[i] - values[i - 1]) for i in range(len(values) - period, len(values)))


def rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) < period + 1:
        return None
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    recent = changes[-period:]
    gains = mean(max(x, 0.0) for x in recent)
    losses = mean(max(-x, 0.0) for x in recent)
    if losses == 0:
        return 100.0 if gains > 0 else 50.0
    return 100 - (100 / (1 + gains / losses))


def _slope(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = mean(values)
    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    return numerator / denominator if denominator else 0.0


def _base(signal: str, reason: str, samples: int) -> dict:
    return {
        'signal': signal,
        'reason': reason,
        'entry': None,
        'tp': [],
        'stop': None,
        'confidence': 0,
        'setup_strength': 0,
        'samples': samples,
        'rsi': None,
        'trend': 'NEUTRAL',
        'risk_reward': None,
    }


def analyze(samples: list[dict]) -> dict:
    prices = [float(x['price']) for x in samples if x.get('price') is not None]
    count = len(prices)
    if count < MIN_MARKET_SAMPLES:
        return _base('HOLD', 'DATA_GAP', count)

    e20, e50 = ema(prices, 20), ema(prices, 50)
    a, rs = atr(prices), rsi(prices)
    if e20 is None or e50 is None or a is None or rs is None or a <= 0:
        return _base('HOLD', 'INDICATOR_UNAVAILABLE', count)

    last = prices[-1]
    recent = prices[-20:]
    prior = prices[-40:-20]
    slope = _slope(recent)
    slope_norm = slope / a

    long_trend = e20 > e50 and last > e20 and slope_norm > 0.05
    short_trend = e20 < e50 and last < e20 and slope_norm < -0.05

    recent_high = max(prior) if prior else last
    recent_low = min(prior) if prior else last
    long_structure = last >= recent_high
    short_structure = last <= recent_low

    # RSI is used as a confirmation filter, not as a standalone entry trigger.
    long_momentum = 52 <= rs <= 72
    short_momentum = 28 <= rs <= 48

    if not ((long_trend and long_structure and long_momentum) or (short_trend and short_structure and short_momentum)):
        trend = 'BULLISH' if e20 > e50 else 'BEARISH' if e20 < e50 else 'NEUTRAL'
        result = _base('HOLD', 'NO_FULL_CONFIRMATION', count)
        result['entry'] = round(last, 2)
        result['trend'] = trend
        result['rsi'] = round(rs, 1)
        result['setup_strength'] = 50
        result['confidence'] = 50
        return result

    direction = 'LONG' if long_trend else 'SHORT'
    trend = 'BULLISH' if direction == 'LONG' else 'BEARISH'

    trend_score = min(35, abs(e20 - e50) / a * 20)
    slope_score = min(25, abs(slope_norm) * 80)
    momentum_score = 20 if (long_momentum if direction == 'LONG' else short_momentum) else 0
    structure_score = 20
    strength = int(round(min(95, max(55, 55 + trend_score + slope_score + momentum_score + structure_score - 55))))

    risk = a * 1.2
    reward_multipliers = (1.5, 2.5, 3.5)
    stop = last - risk if direction == 'LONG' else last + risk
    targets = [last + a * m if direction == 'LONG' else last - a * m for m in reward_multipliers]

    return {
        'signal': direction,
        'reason': 'TREND_MOMENTUM_STRUCTURE',
        'entry': round(last, 2),
        'tp': [round(x, 2) for x in targets],
        'stop': round(stop, 2),
        'confidence': strength,
        'setup_strength': strength,
        'samples': count,
        'rsi': round(rs, 1),
        'trend': trend,
        'risk_reward': '1:1.25 / 1:2.08 / 1:2.92',
    }
