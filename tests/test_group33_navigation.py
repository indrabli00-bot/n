"""Group 3.3 regression checks for canonical persistent navigation."""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:TEST")
os.environ.setdefault("GOLDAPI_API_KEY", "phase3-test-goldapi-key")
os.environ.setdefault("WHOP_WEBHOOK_SECRET", "phase3-test-secret")

import terminal_style as ts


class Group33NavigationTests(unittest.TestCase):
    def test_main_keyboard_has_persistent_nav(self):
        import main
        fake = type("U", (), {"effective_user": None})()
        keyboard = main.home_keyboard(fake)
        row = keyboard.inline_keyboard[-1]
        self.assertEqual([b.callback_data for b in row], ["nav:home", "screen:account"])
        self.assertFalse(any(b.callback_data == "nav:back" for r in keyboard.inline_keyboard for b in r))

    def test_all_main_keyboard_helpers_append_persistent_nav(self):
        source = Path("main.py").read_text()
        names = ["home_keyboard", "price_keyboard", "signal_keyboard", "account_keyboard", "access_keyboard", "analysis_keyboard", "settings_keyboard", "language_keyboard", "support_keyboard"]
        for name in names:
            start = source.index(f"def {name}(")
            end = source.find("\ndef ", start + 1)
            if end == -1:
                end = source.find("\nasync def ", start + 1)
            segment = source[start:end]
            self.assertIn("return _keyboard(", segment, name)

    def test_persistent_navigation_shape(self):
        keyboard = ts.render_persistent_nav("en")
        row = keyboard.inline_keyboard[-1]
        self.assertEqual(len(row), 2)
        self.assertEqual(row[0].callback_data, "nav:home")
        self.assertEqual(row[1].callback_data, "screen:account")
        self.assertIn("🏠", row[0].text)
        self.assertIn("👨‍💼", row[1].text)

    def test_canonical_box_has_fixed_geometry(self):
        box = ts.render_terminal_box("A" * 40)
        rows = box.splitlines()
        self.assertTrue(rows)
        self.assertTrue(all(len(row) == ts.PANEL_W for row in rows))
        self.assertEqual(rows[0], "┍" + "━" * 34 + "┑")
        self.assertEqual(rows[-1], "┕" + "━" * 34 + "┙")
        self.assertEqual(len(rows[1]), 36)
        self.assertEqual(len(rows[2]), 36)

    def test_long_token_is_fully_preserved(self):
        token = "A" * 40
        wrapped = ts.word_wrap(token, 34)
        self.assertEqual(wrapped, ["A" * 34, "A" * 6])
        self.assertEqual("".join(wrapped), token)


if __name__ == "__main__":
    unittest.main()
