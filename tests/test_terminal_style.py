import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:TEST")
os.environ.setdefault("GOLDAPI_API_KEY", "phase0-test-goldapi-key")
os.environ.setdefault("WHOP_WEBHOOK_SECRET", "whsec_phase2-test-secret")
import i18n
import terminal_style as ts

class TerminalStyleTests(unittest.TestCase):
    def test_terminal_has_no_decorative_border(self):
        content = "[ SYSTEM ]: TEST"
        box = ts.render_terminal_box(content)
        self.assertEqual(box, content)
        self.assertNotIn("┍", box)
        self.assertNotIn("┙", box)
        self.assertNotIn("│", box)
    def test_word_wrap_explicit_max_width(self):
        result = ts.word_wrap("A" * 40, 34)
        self.assertEqual([len(x) for x in result], [34, 6])
        self.assertEqual("".join(result), "A" * 40)
    def test_terminal_wrap_respects_explicit_max_width(self):
        self.assertEqual([len(x) for x in ts.render_terminal_box("A" * 40, 34).splitlines()], [34, 6])
    def test_boot_and_errors(self):
        self.assertIn("[ SYSTEM ]: INITIALIZING NEURAL GOLD", ts.boot(True))
        self.assertIn("[ ACCESS ]: PENDING // CLEARANCE REQUIRED", ts.boot(False))
        self.assertIn("[ ERROR ]: DATA_GAP_DETECTED", ts.data_gap())
        self.assertIn("[ FAULT ]: LINK_TIMEOUT // RETRYING...", ts.link_timeout())
    def test_localized_guides(self):
        for lang in ("en", "vi", "hi", "id", "zh"):
            for key in ("select_plan", "use_package_buttons", "paid", "verified_auto", "activate"):
                self.assertIn(i18n.t(lang, key), ts.pay_guide(lang))
    def test_stamp_shape(self):
        self.assertTrue(ts.stamp().startswith("[ ") and ts.stamp().endswith(" UTC ]"))
