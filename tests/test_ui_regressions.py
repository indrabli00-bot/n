"""UI regression tests: bug header 28x (implicit-concat dengan operator *) tidak boleh terulang."""
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
import auth  # noqa: E402

database.init_db()
import main as mm  # noqa: E402  (setelah install() agar render_* = versi premium)


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
    def test_home_header_rendered_once_and_divider_36(self):
        """Konsol aktif: header OPERATOR CONSOLE tepat 1x + divider 36 char."""
        auth.verify_token = lambda uid: (True, "ok")
        m = M()
        asyncio.run(mm.render_home(U(m, Q(m)), None))
        txt = m.sent[0][0]
        self.assertEqual(txt.count("OPERATOR CONSOLE"), 1, "header terduplikasi (implicit-concat bug)")
        dividers = [line for line in txt.split("\n") if set(line) == {"━"}]
        self.assertTrue(dividers and len(dividers[0]) == 36, f"divider bukan 36: {dividers}")

    def test_start_inactive_lands_on_console_with_pending_status(self):
        """/start user nonaktif -> konsol 8 tombol dengan status PENDING yang jujur (bukan GRANTED palsu)."""
        auth.verify_token = lambda uid: (False, "token_invalid")
        m = M("/start")
        asyncio.run(mm.start_command(U(m, None), None))
        txt, kb = m.sent[-1]
        self.assertIn("OPERATOR CONSOLE", txt)
        self.assertIn("PENDING // CLEARANCE REQUIRED", txt)
        self.assertNotIn("GRANTED. WELCOME, OPERATOR.", txt)
        self.assertNotIn("SELECT PACKAGE", txt)
        self.assertEqual(len(kb.inline_keyboard), 5)  # menu 8 tombol

    def test_start_active_lands_on_console(self):
        """/start user aktif -> konsol operator."""
        auth.verify_token = lambda uid: (True, "ok")
        m = M("/start")
        asyncio.run(mm.start_command(U(m, None), None))
        txt = m.sent[-1][0]
        self.assertIn("OPERATOR CONSOLE", txt)
        self.assertIn("GRANTED. WELCOME, OPERATOR.", txt)


if __name__ == "__main__":
    unittest.main()
