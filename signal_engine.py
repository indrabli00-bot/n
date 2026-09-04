from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean

from config import MARKET_POLL_SECONDS, MIN_MARKET_SAMPLES

MIN_COMPLETED_CANDLES = 50
MAX_SAMPLE_GAP_SECONDS = max(180, MARKET_POLL_SECONDS * 3)


def ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    multiplier = 2 / (period + 1)
    value = mean(values[:period])
    for current in values[period:]:
        value = current * multiplier + value * (1 - multiplier)
    return value


def atr(candles: list[dict], period: int = 14) -> float | None:
    if len(candles) < period + 1:
        return None
    true_ranges = []
    for index in range(1, len(candles)):
        current = candles[index]
        previous_close = candles[index - 1]['close']
        true_ranges.append(
            max(
                current['high'] - current['low'],
                abs(current['high'] - previous_close),
                abs(current['low'] - previous_close),
            )
        )
    return mean(true_ranges[-period:])


def rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) < period + 1:
        return None
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    recent = changes[-period:]
    gains = mean(max(change, 0.0) for change in recent)
    losses = mean(max(-change, 0.0) for change in recent)
    if losses == 0:
        return 100.0 if gains > 0 else 50.0
    return 100 - (100 / (1 + gains / losses))


def _slope(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = mean(values)
    numerator = sum((i - x_mean) * (value - y_mean) for i, value in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    return numerator / denominator if denominator else 0.0


def _timestamp(sample: dict) -> float | None:
    value = sample.get('ts')
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()
    return float(value)


def _has_acceptable_sampling(samples: list[dict]) -> bool:
    timestamps = [_timestamp(sample) for sample in samples]
    if any(value is None for value in timestamps):
        return True
    return all(
        0 < current - previous <= MAX_SAMPLE_GAP_SECONDS
        for previous, current in zip(timestamps, timestamps[1:])
    )


def _ordered_samples(samples: list[dict]) -> list[dict]:
    if not samples or not all(sample.get('ts') is not None for sample in samples):
        return list(samples)
    return sorted(samples, key=lambda sample: _timestamp(sample) or 0.0)


def _candles(samples: list[dict], bucket_seconds: int = 300) -> list[dict]:
    """Aggregate timestamped spot samples into deterministic 5-minute OHLC candles."""
    samples = _ordered_samples(samples)
    if not samples or not all(x.get('ts') is not None for x in samples):
        return [
            {
                'open': float(sample['price']),
                'high': float(sample['price']),
                'low': float(sample['price']),
                'close': float(sample['price']),
            }
            for sample in samples
            if sample.get('price') is not None
        ]

    candles: list[dict] = []
    current_key = None
    current = None
    for item in samples:
        price = item.get('price')
        timestamp = _timestamp(item)
        if price is None or timestamp is None:
            continue
        key = int(timestamp // bucket_seconds)
        if key != current_key:
            if current is not None:
                candles.append(current)
            current_key = key
            current = {
                'open': float(price),
                'high': float(price),
                'low': float(price),
                'close': float(price),
            }
            continue

        price = float(price)
        current['high'] = max(current['high'], price)
        current['low'] = min(current['low'], price)
        current['close'] = price

    if current is not None:
        candles.append(current)
    return candles


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
        'timeframe': 'M5',
    }


def analyze(samples: list[dict]) -> dict:
    ordered = _ordered_samples(samples)
    raw_prices = [float(sample['price']) for sample in ordered if sample.get('price') is not None]
    count = len(raw_prices)
    if count < MIN_MARKET_SAMPLES:
        return _base('HOLD', 'DATA_GAP', count)
    if not _has_acceptable_sampling(ordered):
        return _base('HOLD', 'DATA_GAP', count)

    candles = _candles(ordered)
    if all(sample.get('ts') is not None for sample in ordered) and len(candles) > 1:
        candles = candles[:-1]
    if len(candles) < MIN_COMPLETED_CANDLES:
        return _base('HOLD', 'DATA_GAP', count)

    prices = [candle['close'] for candle in candles]
    e20, e50 = ema(prices, 20), ema(prices, 50)
    average_true_range, relative_strength = atr(candles), rsi(prices)
    if e20 is None or e50 is None or average_true_range is None or relative_strength is None:
        return _base('HOLD', 'INDICATOR_UNAVAILABLE', count)
    if average_true_range <= 0:
        return _base('HOLD', 'INDICATOR_UNAVAILABLE', count)

    last = prices[-1]
    recent = prices[-20:]
    prior_candles = candles[-40:-20]
    prior_high = max(candle['high'] for candle in prior_candles) if prior_candles else last
    prior_low = min(candle['low'] for candle in prior_candles) if prior_candles else last
    structure_range = max(prior_high - prior_low, average_true_range)
    slope_norm = _slope(recent) / average_true_range

    long_trend = e20 > e50 and last > e20 and slope_norm > 0.05
    short_trend = e20 < e50 and last < e20 and slope_norm < -0.05
    long_structure = last >= prior_high
    short_structure = last <= prior_low
    long_momentum = 52 <= relative_strength <= 72
    short_momentum = 28 <= relative_strength <= 48

    if not (
        (long_trend and long_structure and long_momentum)
        or (short_trend and short_structure and short_momentum)
    ):
        trend = 'BULLISH' if e20 > e50 else 'BEARISH' if e20 < e50 else 'NEUTRAL'
        result = _base('HOLD', 'NO_FULL_CONFIRMATION', count)
        result.update({
            'entry': round(last, 2),
            'trend': trend,
            'rsi': round(relative_strength, 1),
            'setup_strength': 50,
            'confidence': 50,
        })
        return result

    direction = 'LONG' if long_trend else 'SHORT'
    trend = 'BULLISH' if direction == 'LONG' else 'BEARISH'
    trend_score = min(35, abs(e20 - e50) / average_true_range * 20)
    slope_score = min(25, abs(slope_norm) * 80)
    strength = int(round(min(95, max(55, 40 + trend_score + slope_score))))

    if direction == 'LONG':
        stop = min(prior_low, last - average_true_range * 0.8)
        risk = last - stop
        targets = [
            last + max(average_true_range, structure_range * 0.5),
            last + max(average_true_range * 1.5, structure_range),
            last + max(average_true_range * 2.0, structure_range * 1.5),
        ]
    else:
        stop = max(prior_high, last + average_true_range * 0.8)
        risk = stop - last
        targets = [
            last - max(average_true_range, structure_range * 0.5),
            last - max(average_true_range * 1.5, structure_range),
            last - max(average_true_range * 2.0, structure_range * 1.5),
        ]

    if risk <= 0:
        return _base('HOLD', 'INVALID_RISK_MODEL', count)

    rr_values = [abs(target - last) / risk for target in targets]
    rr_text = ' / '.join(f'1:{value:.2f}' for value in rr_values)

    return {
        'signal': direction,
        'reason': 'TREND_MOMENTUM_STRUCTURE',
        'entry': round(last, 2),
        'tp': [round(target, 2) for target in targets],
        'stop': round(stop, 2),
        'confidence': strength,
        'setup_strength': strength,
        'samples': count,
        'rsi': round(relative_strength, 1),
        'trend': trend,
        'risk_reward': rr_text,
        'timeframe': 'M5',
    }
