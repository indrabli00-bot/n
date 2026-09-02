from smc_engine import calculate_rsi, detect_fvg, check_candle_pattern, detect_liquidity_grab

def c(o,h,l,cl): return {"open":o,"high":h,"low":l,"close":cl}

def test_rsi_flat_is_neutral():
    candles=[c(100,101,99,100)]*15
    assert calculate_rsi(candles)==100.0

def test_bullish_fvg_unfilled():
    candles=[c(100,101,99,100),c(100,103,99.5,102),c(102,104,102.6,103)]
    assert detect_fvg(candles)==("BULLISH_FVG",1)

def test_filled_fvg_is_rejected():
    candles=[c(100,101,99,100),c(100,103,99.5,102),c(102,104,102.6,103),c(103,105,101,104)]
    assert detect_fvg(candles)==(None,0)

def test_bullish_engulfing():
    candles=[c(102,103,99,100),c(99,104,98,103)]
    assert check_candle_pattern(candles)==("BULLISH_ENGULF",2)

def test_bearish_liquidity_grab():
    candles=[c(100,101,99,100)]*8
    candles += [c(100,103,99.5,102), c(102,105,101.8,101)]
    candles[-2]["high"]=104
    candles[-2]["open"]=103.5
    candles[-2]["close"]=101.5
    candles[-2]["low"]=101
    assert detect_liquidity_grab(candles)==("BEARISH_GRAB",2)
