import base64
import os
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:TEST")
os.environ.setdefault("GOLDAPI_API_KEY", "phase0-test-goldapi-key")
os.environ.setdefault(
    "WHOP_WEBHOOK_SECRET",
    "whsec_" + base64.b64encode(b"phase2-test-secret").decode().rstrip("="),
)

import i18n
import terminal_style


class ActionGuidanceLocalizationTests(unittest.TestCase):
    LANGS = ("en", "id", "vi", "hi", "zh")

    def test_terminal_style_has_no_action_step_catalog(self):
        source = pathlib.Path(__file__).resolve().parents[1].joinpath("terminal_style.py").read_text(encoding="utf-8")
        self.assertNotIn("_BUY_STEPS", source)
        self.assertNotIn("_PAY_STEPS", source)

    def test_buy_guide_uses_localized_catalog(self):
        for lang in self.LANGS:
            output = terminal_style.buy_guide(lang)
            self.assertIn(i18n.t(lang, "select_plan"), output)
            self.assertIn(i18n.t(lang, "use_package_buttons"), output)
            self.assertIn(i18n.t(lang, "paid"), output)

    def test_pay_guide_uses_localized_catalog(self):
        for lang in self.LANGS:
            output = terminal_style.pay_guide(lang)
            for key in ("select_plan", "use_package_buttons", "paid", "verified_auto", "activate"):
                self.assertIn(i18n.t(lang, key), output)


if __name__ == "__main__":
    unittest.main()
