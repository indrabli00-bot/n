import publisher


def test_repeated_same_direction_is_not_republished(monkeypatch):
    state = {'fingerprint': None}
    monkeypatch.setattr(publisher, 'last_published_fingerprint', lambda: state['fingerprint'])
    long_signal = {'signal': 'LONG'}
    assert publisher.should_publish(long_signal) is True
    state['fingerprint'] = publisher.fingerprint(long_signal)
    assert publisher.should_publish({'signal': 'LONG', 'entry': 9999}) is False


def test_direction_change_is_published(monkeypatch):
    long_signal = {'signal': 'LONG'}
    monkeypatch.setattr(publisher, 'last_published_fingerprint', lambda: publisher.fingerprint(long_signal))
    assert publisher.should_publish({'signal': 'SHORT'}) is True


def test_hold_is_never_published(monkeypatch):
    monkeypatch.setattr(publisher, 'last_published_fingerprint', lambda: None)
    assert publisher.should_publish({'signal': 'HOLD'}) is False
