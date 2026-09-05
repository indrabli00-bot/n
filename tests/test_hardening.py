import asyncio
from datetime import datetime, timedelta, timezone

import access
import app as app_module
import market


class FakeBot:
    async def get_chat_member(self, chat_id, telegram_id):
        class Member:
            status = 'member'

        return Member()


def test_access_cache_is_bounded():
    access._cache.clear()
    original_max = access.MAX_CACHE_ENTRIES
    access.MAX_CACHE_ENTRIES = 3
    try:
        bot = FakeBot()
        for telegram_id in range(10):
            asyncio.run(access.channel_member(bot, telegram_id))
        assert len(access._cache) <= 3
    finally:
        access.MAX_CACHE_ENTRIES = original_max
        access._cache.clear()


def test_future_market_timestamp_is_clamped_to_now():
    before = datetime.now(timezone.utc)
    result = market._response_timestamp(
        (before + timedelta(days=1)).isoformat()
    )
    after = datetime.now(timezone.utc)
    assert before <= result <= after


class _FakeTelegramApp:
    def __init__(self):
        self.bot = self
        self.initialized = False
        self.started = False
        self.shutdown_called = False
        self.stop_called = False

    async def initialize(self):
        self.initialized = True

    async def start(self):
        self.started = True

    async def set_webhook(self, **kwargs):
        raise RuntimeError('webhook_setup_failed')

    async def stop(self):
        self.stop_called = True

    async def shutdown(self):
        self.shutdown_called = True


async def _exercise_failed_startup(fake):
    original_build = app_module.build_application
    original_validate = app_module.validate
    original_init_db = app_module.database.init_db
    original_init_state = app_module.publisher.init_state
    app_module.build_application = lambda: fake
    app_module.validate = lambda: None
    app_module.database.init_db = lambda: None
    app_module.publisher.init_state = lambda: None
    try:
        async with app_module.lifespan(app_module.app):
            raise AssertionError('lifespan must not yield after webhook setup failure')
    except RuntimeError as exc:
        assert str(exc) == 'webhook_setup_failed'
    finally:
        app_module.build_application = original_build
        app_module.validate = original_validate
        app_module.database.init_db = original_init_db
        app_module.publisher.init_state = original_init_state


def test_failed_telegram_startup_is_cleaned_up():
    fake = _FakeTelegramApp()
    asyncio.run(_exercise_failed_startup(fake))
    assert fake.initialized is True
    assert fake.started is True
    assert fake.stop_called is True
    assert fake.shutdown_called is True
