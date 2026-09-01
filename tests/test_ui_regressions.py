"""Group 3.3 canonical Telegram UI regression tests."""
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

import database
database.init_db()
import auth
import main as mm


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
    def __init__(self, m=None, q=None, language_code="en"):
        self.message = m
        self.callback_query = q
        u = type("EU", (), {})()
        u.id = 42
        u.first_name = "Tester"
        u.username = "tester"
        u.language_code = language_code
        self.effective_user = u


class UIRegressionTests(unittest.TestCase):
    def test_active_home_has_canonical_header_and_clean_terminal(self):
        auth.verify_token = lambda uid: (True, "ok")
        m = M()
        asyncio.run(mm.render_home(U(m, Q(m)), None))
        txt, kb = m.sent[0]
        self.assertEqual(txt.count("NEURAL GOLD v3.2"), 1)
        self.assertEqual(txt.count("OPERATOR :"), 1)
        self.assertEqual(txt.count("STATUS   :"), 1)
        self.assertIn("Active 🟢", txt)
        self.assertIn("<pre>", txt)
        pre = txt[txt.index("<pre>") + 5:txt.index("</pre>")]
        self.assertNotIn("NEURAL GOLD", pre)
        self.assertNotIn("OPERATOR :", pre)
        self.assertNotIn("STATUS   :", pre)
        self.assertNotIn("[ 20", pre)
        self.assertNotIn("┍", pre)
        self.assertNotIn("┕", pre)
        self.assertEqual([b.callback_data for b in kb.inline_keyboard[-1]], ["nav:home", "screen:account"])

    def test_inactive_home_has_pending_terminal_and_canonical_nav(self):
        auth.verify_token = lambda uid: (False, "token_invalid")
        m = M("/start")
        asyncio.run(mm.start_command(U(m, None), None))
        txt, kb = m.sent[-1]
        self.assertEqual(txt.count("NEURAL GOLD v3.2"), 1)
        self.assertIn("Inactive 🔴", txt)
        self.assertIn("PENDING // CLEARANCE", txt)
        self.assertIn("REQUIRED", txt)
        pre = txt[txt.index("<pre>") + 5:txt.index("</pre>")]
        self.assertNotIn("NEURAL GOLD", pre)
        self.assertEqual([b.callback_data for b in kb.inline_keyboard[-1]], ["nav:home", "screen:account"])

    def test_loading_uses_single_canonical_i18n_feedback(self):
        class LoadingQ(Q):
            def __init__(self, m):
                super().__init__(m)
                self.answer_args = None
                self.answer_kwargs = None
            async def answer(self, *a, **k):
                self.answer_args = a
                self.answer_kwargs = k
        m = M()
        q = LoadingQ(m)
        asyncio.run(mm._answer_loading(U(m, q)))
        self.assertEqual(q.answer_args[0], "Loading...")
        self.assertEqual(q.answer_kwargs.get("show_alert"), False)


    def test_all_customer_keyboards_end_with_persistent_nav(self):
        for helper_name in (
            "home_keyboard", "price_keyboard", "signal_keyboard",
            "account_keyboard", "access_keyboard", "analysis_keyboard",
            "settings_keyboard", "language_keyboard", "support_keyboard",
        ):
            helper = getattr(mm, helper_name)
            kb = helper(U(M()))
            self.assertEqual(
                [b.callback_data for b in kb.inline_keyboard[-1]],
                ["nav:home", "screen:account"],
                helper_name,
            )

    def test_terminal_box_uses_explicit_max_width_without_fixed_geometry(self):
        from terminal_style import render_terminal_box
        out = render_terminal_box("A" * 55, 40)
        self.assertEqual([len(x) for x in out.split("\n")], [40, 15])
        self.assertNotIn("┍", out)
        self.assertNotIn("┕", out)


if __name__ == "__main__":
    unittest.main()
