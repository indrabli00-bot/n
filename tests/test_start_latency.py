import asyncio
import importlib
import types
import unittest
from unittest.mock import AsyncMock, patch

from telegram import InlineKeyboardButton


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

        update = FakeUpdate()
        context = FakeContext()

        async def run():
            with patch.object(module, "_initialize_and_refresh", new=AsyncMock()):
                with self.assertRaises(Exception) as raised:
                    await module.handle_start(update, context)
            self.assertEqual(raised.exception.__class__.__name__, "ApplicationHandlerStop")

        asyncio.run(run())
        update.message.reply_text.assert_awaited_once()
        self.assertTrue(context.application.created)

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

    def test_main_keyboard_normalizes_tuple_navigation_rows(self):
        module = importlib.import_module("main")
        update = types.SimpleNamespace()
        nav_button = InlineKeyboardButton("MENU", callback_data="nav:home")
        body_row = [InlineKeyboardButton("MODULE", callback_data="screen:price")]
        fake_nav = types.SimpleNamespace(inline_keyboard=((nav_button,),))
        with patch.object(module.ts, "render_persistent_nav", return_value=fake_nav), patch.object(module, "_lang", return_value="en"):
            nav = module._persistent_nav(update)
            markup = module._keyboard(update, [body_row])
        self.assertIsInstance(nav, list)
        self.assertIsInstance(nav[0], InlineKeyboardButton)
        self.assertEqual(len(markup.inline_keyboard), 2)
        self.assertEqual(markup.inline_keyboard[1][0].callback_data, "nav:home")


if __name__ == "__main__":
    unittest.main()
