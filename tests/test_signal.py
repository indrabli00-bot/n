from signal_engine import analyze


def samples(n=300, start=2000):
    pattern = [0.20, 0.05, -0.10, 0.15, -0.08, 0.10, -0.05]
    prices = [start]
    for i in range(n):
        prices.append(prices[-1] + pattern[i % len(pattern)])
    return [{'price': price, 'change_pct': 0} for price in prices]


def short_samples(n=300, start=2000):
    return [{'price': 4000 - (x['price'] - 2000), 'change_pct': 0} for x in samples(n, start)]


def flat_samples(n=300, start=2000):
    return [{'price': start, 'change_pct': 0} for _ in range(n)]


def test_data_gap():
    r = analyze(samples(20)); assert r['signal'] == 'HOLD' and r['reason'] == 'DATA_GAP'


def test_long_signal_has_risk_controls():
    r = analyze(samples())
    assert r['signal'] == 'LONG'
    assert r['stop'] < r['entry']
    assert len(r['tp']) == 3
    assert 55 <= r['setup_strength'] <= 95
    assert r['rsi'] is not None


def test_short_signal_has_risk_controls():
    r = analyze(short_samples())
    assert r['signal'] == 'SHORT'
    assert r['stop'] > r['entry']
    assert len(r['tp']) == 3


def test_flat_market_holds():
    r = analyze(flat_samples())
    assert r['signal'] == 'HOLD'
    assert r['reason'] in {'INDICATOR_UNAVAILABLE', 'NO_FULL_CONFIRMATION'}
