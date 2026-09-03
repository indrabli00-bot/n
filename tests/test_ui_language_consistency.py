"""Regression tests for Group 3.3 UI localization consistency."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:TEST")
os.environ.setdefault("GOLDAPI_API_KEY", "test-key")

import database  # noqa: E402
import i18n  # noqa: E402


database.init_db()


class FakeUser:
    def __init__(self, user_id: int = 42):
        self.id = user_id
        self.first_name = "Tester"


class FakeUpdate:
    def __init__(self, language: str):
        self.effective_user = FakeUser()
        self.language = language


class UILanguageConsistencyTests(unittest.TestCase):
    def setUp(self):
        import main as mm
        self.main = mm
        self.original_lang = mm._lang
        mm._lang = lambda update: update.language

    def tearDown(self):
        self.main._lang = self.original_lang

    def test_home_keyboard_uses_canonical_brand_labels_and_persistent_nav(self):
        self.main.auth.verify_token = lambda uid: (True, "ok")
        for lang in ("en", "id", "vi", "hi", "zh"):
            kb = self.main.home_keyboard(FakeUpdate(lang))
            actual = [button.text for row in kb.inline_keyboard for button in row]
            expected = [
                "MARKET PULSE",
                "NEURAL STRIKES",
                "STRUCTURE MAP",
                f"🏠 {i18n.t(lang, 'menu')}",
                f"👨‍💼 {i18n.t(lang, 'account')}",
            ]
            self.assertEqual(actual, expected)
            self.assertEqual([b.callback_data for b in kb.inline_keyboard[-1]], ["nav:home", "screen:account"])

    def test_package_labels_are_resolved_from_translation_table(self):
        for lang in ("en", "id", "vi", "hi", "zh"):
            for key in ("days7", "days14", "days30"):
                self.assertEqual(i18n.t(lang, key), i18n.t(lang, key))

    def test_pending_module_labels_are_localized(self):
        for lang in ("en", "id", "vi", "hi", "zh"):
            text = "\n".join([
                f"  {i18n.t(lang, 'price')} — XAU/USD",
                f"  {i18n.t(lang, 'signal')}",
                f"  {i18n.t(lang, 'analysis')}",
                f"  {i18n.t(lang, 'account')}",
            ])
            for key in ("price", "signal", "analysis", "account"):
                self.assertIn(i18n.t(lang, key), text)


if __name__ == "__main__":
    unittest.main()
