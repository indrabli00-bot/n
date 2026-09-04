from signal_engine import analyze

def samples(n=300, start=2000):
    return [{'price': start + i*0.2, 'change_pct': 0} for i in range(n)]

def test_data_gap():
    r = analyze(samples(20)); assert r['signal'] == 'HOLD' and r['reason'] == 'DATA_GAP'

def test_long_signal():
    r = analyze(samples()); assert r['signal'] == 'LONG' and r['stop'] < r['entry']
