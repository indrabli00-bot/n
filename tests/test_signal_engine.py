from datetime import datetime, timedelta, timezone

import signal_engine


def _samples(count: int, gap_seconds: int = 60) -> list[dict]:
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    return [
        {
            'ts': start + timedelta(seconds=index * gap_seconds),
            'price': 3500 + index * 0.5,
        }
        for index in range(count)
    ]


def test_atr_uses_true_range():
    candles = [
        {'open': 100.0, 'high': 105.0, 'low': 99.0, 'close': 104.0},
        {'open': 104.0, 'high': 110.0, 'low': 103.0, 'close': 109.0},
    ]
    assert signal_engine.atr(candles, period=1) == 7.0


def test_large_sampling_gap_forces_data_gap():
    samples = _samples(300)
    samples[150]['ts'] += timedelta(minutes=10)
    result = signal_engine.analyze(samples)
    assert result['signal'] == 'HOLD'
    assert result['reason'] == 'DATA_GAP'


def test_unsorted_timestamps_are_normalized():
    samples = _samples(300)
    samples[100], samples[101] = samples[101], samples[100]
    result = signal_engine.analyze(samples)
    assert result['reason'] != 'DATA_GAP'


def test_mixed_valid_and_missing_timestamps_force_data_gap():
    samples = _samples(300)
    samples[150]['ts'] = None
    result = signal_engine.analyze(samples)
    assert result['signal'] == 'HOLD'
    assert result['reason'] == 'DATA_GAP'


def test_invalid_timestamp_forces_data_gap():
    samples = _samples(300)
    samples[150]['ts'] = 'not-a-timestamp'
    result = signal_engine.analyze(samples)
    assert result['signal'] == 'HOLD'
    assert result['reason'] == 'DATA_GAP'


def test_non_finite_timestamp_forces_data_gap():
    samples = _samples(300)
    samples[150]['ts'] = float('nan')
    result = signal_engine.analyze(samples)
    assert result['signal'] == 'HOLD'
    assert result['reason'] == 'DATA_GAP'
