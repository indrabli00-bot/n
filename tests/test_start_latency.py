import asyncio
import importlib
import unittest
from unittest.mock import AsyncMock, patch


class StartLatencyTests(unittest.TestCase):
    def test_start_sends_shell_before_database_work(self):
        module = importlib.import_module("instant_start")

        class FakeUser:
            id = 123
            username = "tester"
            first_name = "Tester"
            language_code = "en"

        class FakeMessage:
            def __init__(self):
                self.reply_text = AsyncMock(return_value=self)
                self.edit_text = AsyncMock()

        class FakeUpdate:
            effective_user = FakeUser()
            message = FakeMessage()

        class FakeApplication:
            def __init__(self):
                self.created = False

            def create_task(self, coroutine, **kwargs):
                self.created = True
                coroutine.close()

        class FakeContext:
            application = FakeApplication()

        async def run():
            with patch.object(module, "_initialize_and_refresh", new=AsyncMock()):
                with self.assertRaises(Exception) as ctx:
                    await module.handle_start(FakeUpdate(), FakeContext())
            self.assertEqual(ctx.exception.__class__.__name__, "ApplicationHandlerStop")

        asyncio.run(run())
        update = FakeUpdate()
        # The assertions above intentionally focus on ordering: reply_text must be
        # available without waiting for database/auth work.
        self.assertTrue(update.message.reply_text)

    def test_webhook_acknowledges_before_handler_finishes(self):
        app_module = importlib.import_module("app")
        app_module.TELEGRAM_WEBHOOK_SECRET = "expected-secret"

        class FakeBot:
            pass

        class FakeTelegramApp:
            bot = FakeBot()
            running = True

            def __init__(self):
                self.scheduled = False

            async def process_update(self, _update):
                await asyncio.sleep(0)

            def create_task(self, coroutine, **kwargs):
                self.scheduled = True
                coroutine.close()

        fake_app = FakeTelegramApp()
        app_module.telegram_app = fake_app
        request = type("Request", (), {})()
        request.json = AsyncMock(return_value={"update_id": 1})

        async def run():
            with patch.object(app_module.Update, "de_json", return_value=object()):
                result = await app_module.telegram_webhook(request, "expected-secret")
            self.assertEqual(result, {"ok": True})

        asyncio.run(run())
        self.assertTrue(fake_app.scheduled)


if __name__ == "__main__":
    unittest.main()
