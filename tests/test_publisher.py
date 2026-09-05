import asyncio

import publisher


class FakeBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, chat_id, text, parse_mode=None):
        self.messages.append((chat_id, text, parse_mode))


def _run(candidate, monkeypatch, claim_results, complete=None):
    bot = FakeBot()
    monkeypatch.setattr(publisher.database, 'recent_samples', lambda: [object()])
    monkeypatch.setattr(publisher.signal_engine, 'analyze', lambda samples: candidate)
    claims = iter(claim_results)
    monkeypatch.setattr(publisher, '_claim_publication', lambda direction: next(claims))
    if complete is not None:
        monkeypatch.setattr(publisher, '_complete_publication', complete)
    else:
        monkeypatch.setattr(publisher, '_complete_publication', lambda direction, token: None)
    monkeypatch.setattr(publisher, '_release_publication', lambda token: None)
    result = asyncio.run(
        publisher.evaluate_and_publish(bot, -100123, lambda value: 'signal-body')
    )
    return result, bot


def test_repeated_same_direction_is_not_republished(monkeypatch):
    calls = {'count': 0}

    def claim(direction):
        calls['count'] += 1
        return 'token' if calls['count'] == 1 else None

    bot = FakeBot()
    monkeypatch.setattr(publisher.database, 'recent_samples', lambda: [object()])
    monkeypatch.setattr(publisher.signal_engine, 'analyze', lambda samples: {'signal': 'LONG'})
    monkeypatch.setattr(publisher, '_claim_publication', claim)
    monkeypatch.setattr(publisher, '_complete_publication', lambda direction, token: None)
    monkeypatch.setattr(publisher, '_release_publication', lambda token: None)

    first = asyncio.run(publisher.evaluate_and_publish(bot, -100123, lambda value: 'body'))
    second = asyncio.run(publisher.evaluate_and_publish(bot, -100123, lambda value: 'body'))

    assert first['published'] is True
    assert second['published'] is False
    assert second['claimed'] is False
    assert len(bot.messages) == 1


def test_direction_change_is_published(monkeypatch):
    bot = FakeBot()
    candidates = iter([{'signal': 'LONG'}, {'signal': 'SHORT'}])
    monkeypatch.setattr(publisher.database, 'recent_samples', lambda: [object()])
    monkeypatch.setattr(publisher.signal_engine, 'analyze', lambda samples: next(candidates))
    monkeypatch.setattr(publisher, '_claim_publication', lambda direction: direction)
    monkeypatch.setattr(publisher, '_complete_publication', lambda direction, token: None)
    monkeypatch.setattr(publisher, '_release_publication', lambda token: None)

    first = asyncio.run(publisher.evaluate_and_publish(bot, -100123, lambda value: value['signal']))
    second = asyncio.run(publisher.evaluate_and_publish(bot, -100123, lambda value: value['signal']))

    assert first['published'] is True
    assert second['published'] is True
    assert len(bot.messages) == 2
    assert bot.messages[0][1].endswith('LONG')
    assert bot.messages[1][1].endswith('SHORT')


def test_hold_is_never_published(monkeypatch):
    bot = FakeBot()
    monkeypatch.setattr(publisher.database, 'recent_samples', lambda: [object()])
    monkeypatch.setattr(publisher.signal_engine, 'analyze', lambda samples: {'signal': 'HOLD'})
    claim = lambda direction: (_ for _ in ()).throw(AssertionError('HOLD must not claim publication'))
    monkeypatch.setattr(publisher, '_claim_publication', claim)

    result = asyncio.run(publisher.evaluate_and_publish(bot, -100123, lambda value: 'body'))

    assert result['published'] is False
    assert len(bot.messages) == 0


def test_delivery_is_reported_when_state_completion_fails(monkeypatch):
    def fail_completion(direction, token):
        raise RuntimeError('temporary_database_failure')

    result, bot = _run(
        {'signal': 'LONG'},
        monkeypatch,
        ['token'],
        complete=fail_completion,
    )

    assert result['published'] is True
    assert result['state_persisted'] is False
    assert len(bot.messages) == 1
