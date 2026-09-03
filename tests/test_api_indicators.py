from api_handler import _technical_indicators


def candle(i, close):
    return {"time": str(i), "open": close - 0.5, "high": close + 1.0, "low": close - 1.0, "close": close}


def test_indicators_include_ema_and_atr():
    data = _technical_indicators([candle(i, 2300 + i * 0.2) for i in range(60)])
    assert data["ema"] is not None
    assert data["atr"] > 0


def test_macd_signal_is_calculated():
    data = _technical_indicators([candle(i, 2300 + i * 0.2) for i in range(60)])
    assert data["macd_signal"] != 0.0


def test_macd_hist_changes_with_price_series():
    up = _technical_indicators([candle(i, 2300 + i * 0.4) for i in range(60)])
    down = _technical_indicators([candle(i, 2324 - i * 0.4) for i in range(60)])
    assert up["macd_hist"] > 0
    assert down["macd_hist"] < 0


def test_short_series_fails_closed_for_volatility_fields():
    data = _technical_indicators([candle(i, 2300 + i) for i in range(20)])
    assert data["ema"] is None
    assert data["atr"] == 0.0
    assert data["bb_position"] == "Data Unavailable"
    assert data["stoch_k"] is None


def test_atr_uses_true_range_not_zero():
    candles = []
    for i in range(60):
        close = 2300 + i * 0.1
        candles.append({"time": str(i), "open": close, "high": close + 2, "low": close - 1, "close": close + 0.5})
    data = _technical_indicators(candles)
    assert 0 < data["atr"] < 4
