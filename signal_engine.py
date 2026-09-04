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


def _candles(samples: list[dict], bucket_seconds: int = 300) -> list[dict]:
    """Aggregate timestamped spot samples into deterministic 5-minute OHLC candles."""
    if not samples or not all(x.get('ts') is not None for x in samples):
        return [{'open': float(x['price']), 'high': float(x['price']), 'low': float(x['price']), 'close': float(x['price'])}
                for x in samples if x.get('price') is not None]

    candles: list[dict] = []
    current_key = None
    current = None
    for item in samples:
        price = item.get('price')
        ts = item.get('ts')
        if price is None or ts is None:
            continue
        timestamp = ts.timestamp() if hasattr(ts, 'timestamp') else float(ts)
        key = int(timestamp // bucket_seconds)
        if key != current_key:
            if current is not None:
                candles.append(current)
            current_key = key
            p = float(price)
            current = {'open': p, 'high': p, 'low': p, 'close': p}
        else:
            p = float(price)
            current['high'] = max(current['high'], p)
            current['low'] = min(current['low'], p)
            current['close'] = p
    if current is not None:
        candles.append(current)
    return candles


def _base(signal: str, reason: str, samples: int) -> dict:
    return {'signal': signal, 'reason': reason, 'entry': None, 'tp': [], 'stop': None,
            'confidence': 0, 'setup_strength': 0, 'samples': samples, 'rsi': None,
            'trend': 'NEUTRAL', 'risk_reward': None, 'timeframe': 'M5'}


def analyze(samples: list[dict]) -> dict:
    raw_prices = [float(x['price']) for x in samples if x.get('price') is not None]
    count = len(raw_prices)
    if count < MIN_MARKET_SAMPLES:
        return _base('HOLD', 'DATA_GAP', count)

    candles = _candles(samples)
    # The last bucket is normally still forming when the poller evaluates a tick.
    # Exclude it so a signal cannot be confirmed by an incomplete M5 candle.
    if all(x.get('ts') is not None for x in samples) and len(candles) > 1:
        candles = candles[:-1]
    prices = [c['close'] for c in candles]
    if len(prices) < 50:
        return _base('HOLD', 'DATA_GAP', count)

    e20, e50 = ema(prices, 20), ema(prices, 50)
    a, rs = atr(prices), rsi(prices)
    if e20 is None or e50 is None or a is None or rs is None or a <= 0:
        return _base('HOLD', 'INDICATOR_UNAVAILABLE', count)

    last = prices[-1]
    recent = prices[-20:]
    prior_candles = candles[-40:-20]
    prior_high = max(c['high'] for c in prior_candles) if prior_candles else last
    prior_low = min(c['low'] for c in prior_candles) if prior_candles else last
    structure_range = max(prior_high - prior_low, a)
    slope_norm = _slope(recent) / a

    long_trend = e20 > e50 and last > e20 and slope_norm > 0.05
    short_trend = e20 < e50 and last < e20 and slope_norm < -0.05
    long_structure = last >= prior_high
    short_structure = last <= prior_low
    long_momentum = 52 <= rs <= 72
    short_momentum = 28 <= rs <= 48

    if not ((long_trend and long_structure and long_momentum) or (short_trend and short_structure and short_momentum)):
        trend = 'BULLISH' if e20 > e50 else 'BEARISH' if e20 < e50 else 'NEUTRAL'
        result = _base('HOLD', 'NO_FULL_CONFIRMATION', count)
        result.update({'entry': round(last, 2), 'trend': trend, 'rsi': round(rs, 1), 'setup_strength': 50, 'confidence': 50})
        return result

    direction = 'LONG' if long_trend else 'SHORT'
    trend = 'BULLISH' if direction == 'LONG' else 'BEARISH'
    trend_score = min(35, abs(e20 - e50) / a * 20)
    slope_score = min(25, abs(slope_norm) * 80)
    strength = int(round(min(95, max(55, 55 + trend_score + slope_score + 40 - 55))))

    if direction == 'LONG':
        stop = min(prior_low, last - a * 0.8)
        risk = last - stop
        targets = [
            last + max(a, structure_range * 0.5),
            last + max(a * 1.5, structure_range),
            last + max(a * 2.0, structure_range * 1.5),
        ]
    else:
        stop = max(prior_high, last + a * 0.8)
        risk = stop - last
        targets = [
            last - max(a, structure_range * 0.5),
            last - max(a * 1.5, structure_range),
            last - max(a * 2.0, structure_range * 1.5),
        ]

    if risk <= 0:
        return _base('HOLD', 'INVALID_RISK_MODEL', count)

    rr_values = [abs(target - last) / risk for target in targets]
    rr_text = ' / '.join(f'1:{value:.2f}' for value in rr_values)

    return {'signal': direction, 'reason': 'TREND_MOMENTUM_STRUCTURE', 'entry': round(last, 2),
            'tp': [round(x, 2) for x in targets], 'stop': round(stop, 2), 'confidence': strength,
            'setup_strength': strength, 'samples': count, 'rsi': round(rs, 1), 'trend': trend,
            'risk_reward': rr_text, 'timeframe': 'M5'}
