"""Phase 0.0 verification: terminal aesthetic wrappers (terminal_style.py)."""
import base64
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:TEST")
os.environ.setdefault("GOLDAPI_API_KEY", "phase0-test-goldapi-key")
os.environ.setdefault(
    "WHOP_WEBHOOK_SECRET",
    "whsec_" + base64.b64encode(b"phase2-test-secret").decode().rstrip("="),
)

import i18n
import terminal_style as ts


class TerminalStyleTests(unittest.TestCase):
    def test_boot_sequence_matches_spec_a(self):
        granted = ts.boot(granted=True)
        self.assertIn("[ SYSTEM ]: INITIALIZING NEURAL GOLD", granted)
        self.assertIn("[ STATUS ]: SYNCING GLOBAL BULLION RESERVES...", granted)
        self.assertIn("[ ACCESS ]: GRANTED. WELCOME, OPERATOR.", granted)
        pending = ts.boot(granted=False)
        self.assertIn("[ ACCESS ]: PENDING // CLEARANCE REQUIRED", pending)

    def test_intel_report_frame_matches_spec_c(self):
        self.assertEqual(ts.intel_header(), "[ !!! INTELLIGENCE REPORT : XAUUSD !!! ]")
        self.assertIn("Restricted Data. For Operator Eyes Only.", ts.intel_footer())

    def test_error_codes_match_spec_d(self):
        self.assertIn("[ ERROR ]: DATA_GAP_DETECTED", ts.data_gap())
        self.assertIn("[ FAULT ]: LINK_TIMEOUT // RETRYING...", ts.link_timeout())
        self.assertIn("CUSTOM HINT", ts.data_gap(hint="CUSTOM HINT"))

    def test_panel_is_monospace_block(self):
        panel = ts.panel(["  A: 1", "  B: 2"])
        self.assertTrue(panel.startswith("<pre>"))
        self.assertTrue(panel.endswith("</pre>"))
        self.assertIn("\n", panel)

    def test_pay_guide_localized_for_all_languages(self):
        for lang in ("en", "vi", "hi", "id", "zh"):
            guide = ts.pay_guide(lang)
            self.assertIn("[ PAYMENT ]", guide)
            self.assertIn("1.", guide)
            self.assertIn("5.", guide)
            for key in ("select_plan", "use_package_buttons", "paid", "verified_auto", "activate"):
                self.assertIn(i18n.t(lang, key), guide)
            buy = ts.buy_guide(lang)
            self.assertIn("[ PAYMENT ]", buy)
            self.assertIn("3.", buy)
            for key in ("select_plan", "use_package_buttons", "paid"):
                self.assertIn(i18n.t(lang, key), buy)
        self.assertEqual(ts.pay_guide("xx"), ts.pay_guide("en"))

    def test_stamp_shape(self):
        stamp = ts.stamp()
        self.assertTrue(stamp.startswith("[ ") and stamp.endswith(" UTC ]"))
        self.assertEqual(len(stamp), len("[ 2026-08-30 14:00:00 UTC ]"))


if __name__ == "__main__":
    unittest.main()
