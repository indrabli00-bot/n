"""UI regression tests for the canonical Group 3.3 render contract."""
import asyncio
import base64
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:TEST")
os.environ.setdefault("GOLDAPI_API_KEY", "test-key")
os.environ["WHOP_WEBHOOK_SECRET"] = "whsec_" + base64.b64encode(b"phase2-test-secret").decode().rstrip("=")

import database  # noqa: E402
database.init_db()
import auth  # noqa: E402
import main as mm  # noqa: E402


class M:
    def __init__(self, text=None):
        self.text = text
        self.sent = []

    async def reply_text(self, t, parse_mode=None, reply_markup=None):
        self.sent.append((t, reply_markup))


class Q:
    def __init__(self, m):
        self.message = m

    async def answer(self, *a, **k):
        pass

    async def edit_message_text(self, *a, **k):
        raise Exception("edit blocked (simulasi fallback)")


class U:
    def __init__(self, m, q):
        self.message = m
        self.callback_query = q
        u = type("EU", (), {})()
        u.id = 42
        u.first_name = "Tester"
        u.username = "tester"
        u.language_code = "en"
        self.effective_user = u


class UIRegressionTests(unittest.TestCase):
    def test_home_header_rendered_once_and_no_fixed_divider(self):
        auth.verify_token = lambda uid: (True, "ok")
        m = M()
        asyncio.run(mm.render_home(U(m, Q(m)), None))
        txt = m.sent[0][0]
        self.assertEqual(txt.count("OPERATOR CONSOLE"), 1)
        self.assertIn("<pre>", txt)
        dividers = [line for line in txt.split("\n") if set(line) == {"━"}]
        self.assertFalse(dividers)

    def test_start_inactive_lands_on_console_with_pending_status(self):
        auth.verify_token = lambda uid: (False, "token_invalid")
        m = M("/start")
        asyncio.run(mm.start_command(U(m, None), None))
        txt, kb = m.sent[-1]
        self.assertIn("OPERATOR CONSOLE", txt)
        self.assertIn("PENDING // CLEARANCE", txt)
        self.assertIn("REQUIRED", txt)
        self.assertNotIn("GRANTED. WELCOME, OPERATOR.", txt)
        self.assertIn("<pre>", txt)
        button_texts = [b.text for row in kb.inline_keyboard for b in row]
        self.assertTrue(any("7 HARI" in x or "7 DAYS" in x for x in button_texts))
        self.assertTrue(any("14 HARI" in x or "14 DAYS" in x for x in button_texts))
        self.assertTrue(any("30 HARI" in x or "30 DAYS" in x for x in button_texts))
        self.assertEqual([b.callback_data for b in kb.inline_keyboard[-1]], ["nav:home", "screen:account"])

    def test_start_active_lands_on_console(self):
        auth.verify_token = lambda uid: (True, "ok")
        m = M("/start")
        asyncio.run(mm.start_command(U(m, None), None))
        txt = m.sent[-1][0]
        self.assertIn("OPERATOR CONSOLE", txt)
        self.assertIn("GRANTED. WELCOME, OPERATOR.", txt)


if __name__ == "__main__":
    unittest.main()
