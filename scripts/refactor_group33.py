from pathlib import Path
import re
from textwrap import dedent

# Canonical terminal renderer: natural width by default, explicit max_width when needed.
# Render ownership: main.py owns final Telegram presentation.

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

# Inactive users see the package choices immediately while active users keep module actions.
needle = "def home_keyboard(update: Update) -> InlineKeyboardMarkup:\n    lang = _lang(update)\n"
replacement = """def home_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    if not auth.verify_token(update.effective_user.id)[0]:
        import phase2_bot
        telegram_id = update.effective_user.id
        return _keyboard(update, [
            [InlineKeyboardButton(f\"🟢 {t(lang, 'days7')}\", url=phase2_bot.checkout_link(telegram_id, 7))],
            [InlineKeyboardButton(f\"🟡 {t(lang, 'days14')}\", url=phase2_bot.checkout_link(telegram_id, 14))],
            [InlineKeyboardButton(f\"🔵 {t(lang, 'days30')}\", url=phase2_bot.checkout_link(telegram_id, 30))],
        ])
"""
if needle in s:
    s = s.replace(needle, replacement, 1)

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
    canonical = f"{render_header(user, lang)}\\n<pre>{render_terminal_box(body)}</pre>" if user else f"<pre>{render_terminal_box(body)}</pre>"
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
''').lstrip(), encoding='utf-8')

n = Path('tests/test_group33_navigation.py').read_text(encoding='utf-8')
old = '''    def test_canonical_box_has_fixed_geometry(self):
        box = ts.render_terminal_box("A" * 40)
        rows = box.splitlines()
        self.assertTrue(rows)
        self.assertTrue(all(len(row) == ts.PANEL_W for row in rows))
        self.assertEqual(rows[0], "┍" + "━" * 34 + "┑")
        self.assertEqual(rows[-1], "┕" + "━" * 34 + "┙")
        self.assertEqual(len(rows[1]), 36)
        self.assertEqual(len(rows[2]), 36)
'''
new = '''    def test_terminal_box_has_no_fixed_geometry(self):
        box = ts.render_terminal_box("A" * 40)
        self.assertEqual(box, "A" * 40)
        self.assertNotIn("┍", box)
        self.assertNotIn("│", box)
'''
if old in n:
    n = n.replace(old, new)
Path('tests/test_group33_navigation.py').write_text(n, encoding='utf-8')

u = Path('tests/test_ui_regressions.py')
src = u.read_text(encoding='utf-8')
src = src.replace('def test_home_header_rendered_once_and_divider_36(self):', 'def test_home_header_rendered_once_and_no_fixed_divider(self):')
src = src.replace('''        dividers = [line for line in txt.split("\\n") if set(line) == {"━"}]
        self.assertTrue(dividers and len(dividers[0]) == 36, f"divider bukan 36: {dividers}")''', '''        self.assertIn("<pre>", txt)
        dividers = [line for line in txt.split("\\n") if set(line) == {"━"}]
        self.assertFalse(dividers)''')
src = src.replace('''        self.assertNotIn("SELECT PACKAGE", txt)
        self.assertEqual(len(kb.inline_keyboard), 5)  # menu 8 tombol''', '''        self.assertIn("<pre>", txt)
        self.assertIn("7 HARI", txt)
        self.assertIn("14 HARI", txt)
        self.assertIn("30 HARI", txt)
        self.assertEqual([b.callback_data for b in kb.inline_keyboard[-1]], ["nav:home", "screen:account"])''')
u.write_text(src, encoding='utf-8')
