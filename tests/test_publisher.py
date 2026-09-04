import publisher


def test_repeated_same_direction_is_not_republished():
    publisher._last_published_fingerprint = None
    long_signal = {'signal': 'LONG'}
    assert publisher.should_publish(long_signal) is True
    publisher.mark_published(long_signal)
    assert publisher.should_publish({'signal': 'LONG', 'entry': 9999}) is False


def test_direction_change_is_published():
    publisher._last_published_fingerprint = None
    publisher.mark_published({'signal': 'LONG'})
    assert publisher.should_publish({'signal': 'SHORT'}) is True


def test_hold_is_never_published():
    publisher._last_published_fingerprint = None
    assert publisher.should_publish({'signal': 'HOLD'}) is False
