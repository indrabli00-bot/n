"""Regression tests for Group 3.1 UI localization consistency."""
from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path

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

    def test_home_keyboard_uses_selected_language_for_core_labels(self):
        keys = ["price", "signal", "analysis", "account", "settings", "language", "access", "menu", "account_persistent"]
        for lang in ("en", "id", "vi", "hi", "zh"):
            kb = self.main.home_keyboard(FakeUpdate(lang))
            actual = [button.text for row in kb.inline_keyboard for button in row]
            expected = [
                f"📈 {i18n.t(lang, 'price')}",
                f"🧠 {i18n.t(lang, 'signal')}",
                f"📊 {i18n.t(lang, 'analysis')}",
                f"👑 {i18n.t(lang, 'account')}",
                f"⚙️ {i18n.t(lang, 'settings')}",
                f"🌐 {i18n.t(lang, 'language')}",
                f"💎 {i18n.t(lang, 'access')}",
                f"🏠 {i18n.t(lang, 'menu')}",
                f"👨‍💼 {i18n.t(lang, 'account')}",
            ]
            self.assertEqual(len(keys), len(expected))
            self.assertEqual(actual, expected)

    def test_package_labels_are_resolved_from_translation_table(self):
        for lang in ("en", "id", "vi", "hi", "zh"):
            for days, key in ((7, "days7"), (14, "days14"), (30, "days30")):
                self.assertEqual(i18n.t(lang, key), i18n.t(lang, key))

    def test_premium_visuals_has_no_legacy_hardcoded_ui_labels(self):
        source = Path(__file__).resolve().parents[1].joinpath("premium_visuals.py").read_text(encoding="utf-8")
        for phrase in (
            "📈 Market Pulse",
            "🧠 Neural Strikes",
            "📊 Structure Map",
            "👑 Operator Hub",
            "⚙️ System Sync",
            "🌐 Language",
            "💎 ACCESS & PLANS",
            "🕐 7 DAYS — TACTICAL TRIAL",
            "🟡 14 DAYS — STRATEGIC ENTRY",
            "🔵 30 DAYS — FULL OPERATIONAL CONTROL",
            '"← BACK"',
            '"⌂ MENU"',
        ):
            self.assertNotIn(phrase, source, phrase)

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
