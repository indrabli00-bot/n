from pathlib import Path

p = Path('main.py')
s = p.read_text()
start = s.index('def _nav_keyboard(')
end = s.index('async def render_home(', start)
block = '''def _persistent_nav(update: Update) -> list[InlineKeyboardButton]:
    lang = _lang(update)
    return [
        InlineKeyboardButton(f"🏠 {t(lang, 'menu')}", callback_data='nav:home'),
        InlineKeyboardButton(f"👨‍💼 {t(lang, 'account')}", callback_data='screen:account'),
    ]


def _keyboard(update: Update, rows=None) -> InlineKeyboardMarkup:
    keyboard = list(rows or [])
    keyboard.append(_persistent_nav(update))
    return InlineKeyboardMarkup(keyboard)


def home_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    return _keyboard(update, [
        [InlineKeyboardButton(t(lang, 'price'), callback_data='screen:price'), InlineKeyboardButton(t(lang, 'signal'), callback_data='screen:signal')],
        [InlineKeyboardButton(t(lang, 'analysis'), callback_data='screen:analysis'), InlineKeyboardButton(t(lang, 'account'), callback_data='screen:account')],
        [InlineKeyboardButton(t(lang, 'settings'), callback_data='screen:settings'), InlineKeyboardButton(f"🌐 {t(lang, 'language')}", callback_data='settings:language')],
        [InlineKeyboardButton(t(lang, 'access'), callback_data='screen:access')],
    ])


def price_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    if auth.verify_token(update.effective_user.id)[0]:
        return _keyboard(update, [[InlineKeyboardButton(t(lang, 'refresh'), callback_data='screen:price')]])
    import phase2_bot
    telegram_id = update.effective_user.id
    return _keyboard(update, [
        [InlineKeyboardButton(f"🟢 {t(lang, 'days7')}", url=phase2_bot.checkout_link(telegram_id, 7))],
        [InlineKeyboardButton(f"🟡 {t(lang, 'days14')}", url=phase2_bot.checkout_link(telegram_id, 14))],
        [InlineKeyboardButton(f"🔵 {t(lang, 'days30')}", url=phase2_bot.checkout_link(telegram_id, 30))],
    ])


def signal_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    return _keyboard(update, [[InlineKeyboardButton(t(lang, 'new_signal'), callback_data='screen:signal')]])


def account_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    return _keyboard(update, [[InlineKeyboardButton(t(lang, 'refresh_status'), callback_data='screen:account')]])


def access_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    import phase2_bot
    telegram_id = update.effective_user.id
    return _keyboard(update, [
        [InlineKeyboardButton(f"🟢 {t(lang, 'days7')}", url=phase2_bot.checkout_link(telegram_id, 7))],
        [InlineKeyboardButton(f"🟡 {t(lang, 'days14')}", url=phase2_bot.checkout_link(telegram_id, 14))],
        [InlineKeyboardButton(f"🔵 {t(lang, 'days30')}", url=phase2_bot.checkout_link(telegram_id, 30))],
        [InlineKeyboardButton(t(lang, 'activate'), callback_data='action:token'), InlineKeyboardButton(t(lang, 'paid'), callback_data='paid:menu')],
    ])


def analysis_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    return _keyboard(update, [[InlineKeyboardButton(t(lang, 'refresh_analysis'), callback_data='screen:analysis')]])


def settings_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    return _keyboard(update, [
        [InlineKeyboardButton(t(lang, 'interface'), callback_data='noop')],
        [InlineKeyboardButton(t(lang, 'timezone'), callback_data='noop')],
        [InlineKeyboardButton(t(lang, 'data_mode'), callback_data='noop')],
    ])


def language_keyboard(update: Update) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(label, callback_data=data)] for label, data in language_buttons()]
    return _keyboard(update, rows)


def support_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    rows = []
    if ADMIN_TELEGRAM_ID:
        rows.append([InlineKeyboardButton(t(lang, 'contact'), url=f'tg://user?id={ADMIN_TELEGRAM_ID}')])
    return _keyboard(update, rows)

'''
s = s[:start] + block + s[end:]
old = "text = f'{boot(granted=True)}\\n<i>{stamp()}</i>\\n{DIVIDER}\\n\\nOPERATOR: <b>{_safe_user_name(user)}</b>\\nTELEGRAM_ID: <code>{user.id}</code>\\nCLEARANCE: <b>{GOLD} ● {t(_lang(update), 'premium_active')}</b>\\n\\n<b>>> {t(_lang(update), 'select_module')}</b>\\n' + panel(['  01  PRICE     — MARKET PULSE', '  02  SIGNAL    — NEURAL STRIKES', '  03  ANALYSIS  — STRUCTURE MAP', '  04  ACCOUNT   — OPERATOR HUB', '  05  SETTINGS  — SYSTEM SYNC', '  06  SUPPORT   — UPLINK']) + '\\n>> [ CORE ]: ALL MODULES UNLOCKED. AWAITING SELECTION.'"
new = "lang = _lang(update)\n    clearance = t(lang, 'premium_active') if active else '[ ACCESS ]: PENDING // CLEARANCE REQUIRED'\n    text = f'{boot(granted=active)}\\n<i>{stamp()}</i>\\n{DIVIDER}\\n\\nOPERATOR: <b>{_safe_user_name(user)}</b>\\nTELEGRAM_ID: <code>{user.id}</code>\\nCLEARANCE: <b>{GOLD} ● {clearance}</b>\\n\\n<b>>> {t(lang, 'select_module')}</b>\\n' + panel(['  01  PRICE     — MARKET PULSE', '  02  SIGNAL    — NEURAL STRIKES', '  03  ANALYSIS  — STRUCTURE MAP', '  04  ACCOUNT   — OPERATOR HUB', '  05  SETTINGS  — SYSTEM SYNC', '  06  SUPPORT   — UPLINK']) + '\\n>> [ CORE ]: ALL MODULES UNLOCKED. AWAITING SELECTION.'"
assert old in s, 'render_home target not found'
s = s.replace(old, new, 1)
p.write_text(s)

Path('premium_visuals.py').write_text('''"""Deprecated Group 3.3 compatibility module.\n\nCanonical Telegram UI ownership lives in main.py.\n"""\n\ndef install() -> None:\n    """Compatibility no-op retained for older callers."""\n    return None\n''')

app = Path('app.py')
a = app.read_text().replace('import premium_visuals\\n', '').replace('    premium_visuals.install()\\n', '')
app.write_text(a)

t = Path('tests/test_ui_regressions.py')
ts = t.read_text()
ts = ts.replace('import premium_visuals as pv  # noqa: E402\\n', '')
ts = ts.replace('pv.install()\\nimport main as mm  # noqa: E402  (setelah install() agar render_* = versi premium)', 'import main as mm  # noqa: E402')
ts = ts.replace('asyncio.run(pv.render_home(U(m, Q(m)), None))', 'asyncio.run(mm.render_home(U(m, Q(m)), None))')
ts = ts.replace('def test_home_header_rendered_once_and_divider_28(self):', 'def test_home_header_rendered_once_and_divider_36(self):')
ts = ts.replace('divider 28 char', 'divider 36 char').replace('len(dividers[0]) == 28', 'len(dividers[0]) == 36').replace('f"divider bukan 28: {dividers}"', 'f"divider bukan 36: {dividers}"')
t.write_text(ts)

navtest = Path('tests/test_group33_navigation.py')
ns = navtest.read_text()
if 'def test_main_keyboard_has_persistent_nav' not in ns:
    ns = ns.replace('class Group33NavigationTests(unittest.TestCase):', '''class Group33NavigationTests(unittest.TestCase):\n    def test_main_keyboard_has_persistent_nav(self):\n        import main\n        fake = type("U", (), {"effective_user": None})()\n        keyboard = main.home_keyboard(fake)\n        row = keyboard.inline_keyboard[-1]\n        self.assertEqual([b.callback_data for b in row], ["nav:home", "screen:account"])\n        self.assertFalse(any(b.callback_data == "nav:back" for r in keyboard.inline_keyboard for b in r))\n\n''')
navtest.write_text(ns)
