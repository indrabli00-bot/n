import asyncio

import publisher


def test_repeated_same_direction_is_not_republished(monkeypatch):
    state = {'fingerprint': None}
    monkeypatch.setattr(
        publisher,
        'last_published_fingerprint',
        lambda: state['fingerprint'],
    )
    long_signal = {'signal': 'LONG'}
    assert publisher.should_publish(long_signal) is True
    state['fingerprint'] = publisher.fingerprint(long_signal)
    assert publisher.should_publish({'signal': 'LONG', 'entry': 9999}) is False


def test_direction_change_is_published(monkeypatch):
    long_signal = {'signal': 'LONG'}
    monkeypatch.setattr(
        publisher,
        'last_published_fingerprint',
        lambda: publisher.fingerprint(long_signal),
    )
    assert publisher.should_publish({'signal': 'SHORT'}) is True


def test_hold_is_never_published(monkeypatch):
    monkeypatch.setattr(publisher, 'last_published_fingerprint', lambda: None)
    assert publisher.should_publish({'signal': 'HOLD'}) is False


def test_publication_state_retries_after_transient_failure(monkeypatch):
    attempts = {'count': 0}

    def flaky_mark(_candidate):
        attempts['count'] += 1
        if attempts['count'] < 3:
            raise RuntimeError('temporary_database_failure')

    monkeypatch.setattr(publisher, 'mark_published', flaky_mark)
    monkeypatch.setattr(publisher, 'MARK_RETRY_DELAY_SECONDS', 0)

    result = asyncio.run(
        publisher._mark_published_with_retry({'signal': 'LONG'})
    )

    assert result is True
    assert attempts['count'] == 3
