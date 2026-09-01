from pathlib import Path
import re
from textwrap import dedent

p = Path('main.py')
s = p.read_text(encoding='utf-8')
s = re.sub(r'\ndef _nav_keyboard\(.*?\n(?=def |async def )', '\n', s, flags=re.S)
s = re.sub(r'def _persistent_nav\(update: Update\) -> list\[InlineKeyboardButton\]:.*?\n\n\ndef _keyboard', dedent('''
def _persistent_nav(update: Update) -> list[InlineKeyboardButton]:
    lang = _lang(update)
    return list(ts.render_persistent_nav(lang).inline_keyboard[0])


def _keyboard''').strip(), s, flags=re.S)
s = s.replace("InlineKeyboardButton(t(lang, 'back'), callback_data='nav:home')", "")
s = s.replace("await _present(update, text, InlineKeyboardMarkup(rows))", "await _present(update, text, _keyboard(update, rows))")
s = s.replace("await _present(update, text, _nav_keyboard(update))", "await _present(update, text, _keyboard(update))")
s = s.replace("from terminal_style import boot, intel_footer, intel_header, pay_guide, panel, stamp", "from terminal_style import boot, intel_footer, intel_header, pay_guide, panel, render_header, render_terminal_box, stamp")
marker = 'async def _present(update: Update, text: str, keyboard: InlineKeyboardMarkup, edit: bool=True) -> None:'
start = s.index(marker)
end = s.index(chr(10) + 'async def start_command', start)
present = dedent('''
async def _present(update: Update, text: str, keyboard: InlineKeyboardMarkup, edit: bool=True) -> None:
    """Enforce Header -> Terminal -> optional Action, with persistent navigation."""
    query = update.callback_query
    user = update.effective_user
    lang = _lang(update)
    body = re.sub(r"<[^>]+>", "", text)
    body = html.unescape(body).strip()
    body = body.translate(str.maketrans('', '', '┍┑┕┙│◤◥◣◢━─'))
    canonical = f"{render_header(user, lang)}\n<pre>{render_terminal_box(body)}</pre>" if user else f"<pre>{render_terminal_box(body)}</pre>"
    if query and edit:
        try:
            await query.edit_message_text(text=canonical, parse_mode='HTML', reply_markup=keyboard)
            return
        except BadRequest as exc:
            if 'not modified' in str(exc).lower():
                return
            logger.debug('Could not edit callback message: %s', exc)
        except Exception as exc:
            logger.debug('Could not edit callback message: %s', exc)
    try:
        if query and query.message:
            await query.message.reply_text(canonical, parse_mode='HTML', reply_markup=keyboard)
            return
    except Exception as exc:
        logger.debug('Callback reply fallback failed: %s', exc)
    if update.message:
        await update.message.reply_text(canonical, parse_mode='HTML', reply_markup=keyboard)
''').lstrip()
s = s[:start] + present + s[end:]
p.write_text(s, encoding='utf-8')

Path('tests/test_terminal_style.py').write_text(dedent('''
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
        self.assertEqual(ts.render_terminal_box(content), content)
        self.assertNotIn("┍", ts.render_terminal_box(content))
        self.assertNotIn("┙", ts.render_terminal_box(content))
        self.assertNotIn("│", ts.render_terminal_box(content))
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
''').lstrip(), encoding='utf-8')

n = Path('tests/test_group33_navigation.py').read_text(encoding='utf-8')
n = re.sub(r'    def test_canonical_box_has_fixed_geometry\(self\):.*?\n    def test_long_token_is_fully_preserved', dedent('''
    def test_terminal_box_has_no_fixed_geometry(self):
        box = ts.render_terminal_box("A" * 40)
        self.assertEqual(box, "A" * 40)
        self.assertNotIn("┍", box)
        self.assertNotIn("│", box)

    def test_long_token_is_fully_preserved''').lstrip(), n, flags=re.S)
Path('tests/test_group33_navigation.py').write_text(n, encoding='utf-8')
