from smc_engine import calculate_rsi, detect_fvg, check_candle_pattern, generate_signal

def c(o,h,l,cl): return {"open":o,"high":h,"low":l,"close":cl}

def test_rsi_fallback_is_neutral():
    assert calculate_rsi([c(100,101,99,100)]*10)==50.0

def test_bullish_fvg_unfilled():
    candles=[c(100,101,99,100),c(100,103,99.5,102),c(102,104,102.6,103)]
    assert detect_fvg(candles)==("BULLISH_FVG",1)

def test_filled_fvg_is_rejected():
    candles=[c(100,101,99,100),c(100,103,99.5,102),c(102,104,102.6,103),c(103,105,101,104)]
    assert detect_fvg(candles)==(None,0)

def test_bullish_engulfing():
    assert check_candle_pattern([c(102,103,99,100),c(99,104,98,103)])==("BULLISH_ENGULF",2)

def test_bearish_engulfing():
    assert check_candle_pattern([c(99,104,98,103),c(104,105,98,99)])==("BEARISH_ENGULF",2)

def test_neutral_structure_returns_hold_with_confirmation_guidance():
    candles=[c(100+i*0.01,101+i*0.01,99+i*0.01,100+i*0.01) for i in range(25)]
    signal=generate_signal(candles,candles)
    assert signal["direction"]=="HOLD"
    assert any("WAIT FOR 15M BIAS CONFIRMATION" in r for r in signal["reasons"])
    assert signal["tp1"]==signal["tp2"]==signal["tp3"]==signal["sl"]==0.0
