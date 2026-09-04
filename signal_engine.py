from __future__ import annotations
from statistics import mean
from config import MIN_MARKET_SAMPLES

def ema(values: list[float], period: int) -> float | None:
    if len(values) < period: return None
    k = 2 / (period + 1); value = mean(values[:period])
    for v in values[period:]: value = v * k + value * (1-k)
    return value

def atr(values: list[float], period: int = 14) -> float | None:
    if len(values) < period + 1: return None
    return mean(abs(values[i] - values[i-1]) for i in range(len(values)-period, len(values)))

def analyze(samples: list[dict]) -> dict:
    prices = [float(x['price']) for x in samples]
    if len(prices) < MIN_MARKET_SAMPLES:
        return {'signal':'HOLD','reason':'DATA_GAP','entry':None,'tp':[],'stop':None,'confidence':0,'samples':len(prices)}
    e20, e50, a = ema(prices,20), ema(prices,50), atr(prices)
    last = prices[-1]
    if e20 is None or e50 is None or a is None or a <= 0:
        return {'signal':'HOLD','reason':'INDICATOR_UNAVAILABLE','entry':None,'tp':[],'stop':None,'confidence':0,'samples':len(prices)}
    long_bias = e20 > e50 and last > e20
    short_bias = e20 < e50 and last < e20
    recent = prices[-20:]
    structure_long = max(recent[-5:]) > max(recent[:5])
    structure_short = min(recent[-5:]) < min(recent[:5])
    if long_bias and structure_long: direction = 'LONG'
    elif short_bias and structure_short: direction = 'SHORT'
    else:
        return {'signal':'HOLD','reason':'NO_STRUCTURE_CONFIRMATION','entry':last,'tp':[],'stop':None,'confidence':50,'samples':len(prices)}
    strength = abs(e20-e50) / a
    confidence = min(95, max(55, int(55 + strength*15)))
    stop = last - a*1.2 if direction == 'LONG' else last + a*1.2
    targets = [last + a*m if direction == 'LONG' else last-a*m for m in (1.5,2.5,3.5)]
    return {'signal':direction,'reason':'TREND_STRUCTURE_CONFIRMATION','entry':round(last,2),'tp':[round(x,2) for x in targets],'stop':round(stop,2),'confidence':confidence,'samples':len(prices)}
