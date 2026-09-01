from pathlib import Path
import re

ROOT = Path('.')

CANONICAL_SEGMENT = r'''def _is_active(update: Update) -> bool:
    user = update.effective_user
    return bool(user and auth.verify_token(user.id)[0])


def _persistent_nav(update: Update) -> list[InlineKeyboardButton]:
    return list(ts.render_persistent_nav(_lang(update)).inline_keyboard[0])


def _keyboard(update: Update, rows=None) -> InlineKeyboardMarkup:
    keyboard = list(rows or [])
    keyboard.append(_persistent_nav(update))
    return InlineKeyboardMarkup(keyboard)


def _module_button(label: str, callback: str, locked: bool = False) -> InlineKeyboardButton:
    return InlineKeyboardButton(f"🔒 {label}" if locked else label, callback_data=callback)


def home_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    if _is_active(update):
        rows = [[InlineKeyboardButton("MARKET PULSE", callback_data="screen:price"), InlineKeyboardButton("NEURAL STRIKES", callback_data="screen:signal")], [InlineKeyboardButton("STRUCTURE MAP", callback_data="screen:analysis")]]
    else:
        rows = [[_module_button("MARKET PULSE", "screen:price", True), _module_button("NEURAL STRIKES", "screen:signal", True)], [_module_button("STRUCTURE MAP", "screen:analysis", True)], [InlineKeyboardButton(f"💎 {t(lang, 'activate')}", callback_data="screen:activate")]]
    return _keyboard(update, rows)


def _module_nav(update: Update, screen: str) -> list[list[InlineKeyboardButton]]:
    return [[InlineKeyboardButton(t(_lang(update), "refresh"), callback_data=f"refresh:{screen}")], [InlineKeyboardButton("MARKET PULSE", callback_data="screen:price"), InlineKeyboardButton("NEURAL STRIKES", callback_data="screen:signal")], [InlineKeyboardButton("STRUCTURE MAP", callback_data="screen:analysis")]]


def price_keyboard(update: Update) -> InlineKeyboardMarkup:
    rows = _module_nav(update, "price") if _is_active(update) else [[InlineKeyboardButton(f"💎 {t(_lang(update), 'activate')}", callback_data="screen:activate")]]
    return _keyboard(update, rows)


def signal_keyboard(update: Update) -> InlineKeyboardMarkup:
    rows = _module_nav(update, "signal") if _is_active(update) else [[InlineKeyboardButton(f"💎 {t(_lang(update), 'activate')}", callback_data="screen:activate")]]
    return _keyboard(update, rows)


def analysis_keyboard(update: Update) -> InlineKeyboardMarkup:
    rows = _module_nav(update, "analysis") if _is_active(update) else [[InlineKeyboardButton(f"💎 {t(_lang(update), 'activate')}", callback_data="screen:activate")]]
    return _keyboard(update, rows)


def account_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    if _is_active(update):
        rows = [[InlineKeyboardButton("🔄 Tambah masa aktif", callback_data="screen:renew")], [InlineKeyboardButton(f"📊 {t(lang, 'history')}", callback_data="screen:history")]]
    else:
        rows = [[InlineKeyboardButton(f"💎 {t(lang, 'activate')}", callback_data="screen:activate")]]
    return _keyboard(update, rows)


def access_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    import phase2_bot
    tid = update.effective_user.id
    rows = [[InlineKeyboardButton(f"🟢 {t(lang, 'days7')}", url=phase2_bot.checkout_link(tid, 7)), InlineKeyboardButton(f"🟡 {t(lang, 'days14')}", url=phase2_bot.checkout_link(tid, 14))], [InlineKeyboardButton(f"🔵 {t(lang, 'days30')}", url=phase2_bot.checkout_link(tid, 30))]]
    return _keyboard(update, rows)


def settings_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    rows = [[InlineKeyboardButton(t(lang, "interface"), callback_data="noop")], [InlineKeyboardButton(t(lang, "timezone"), callback_data="noop")], [InlineKeyboardButton(t(lang, "data_mode"), callback_data="noop")]]
    if not _is_active(update):
        rows.append([InlineKeyboardButton(f"💎 {t(lang, 'activate')}", callback_data="screen:activate")])
    return _keyboard(update, rows)


def language_keyboard(update: Update) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(label, callback_data=data)] for label, data in language_buttons()]
    if not _is_active(update):
        rows.append([InlineKeyboardButton(f"💎 {t(_lang(update), 'activate')}", callback_data="screen:activate")])
    return _keyboard(update, rows)


def support_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    rows = []
    if ADMIN_TELEGRAM_ID:
        rows.append([InlineKeyboardButton(t(lang, "contact"), url=f"tg://user?id={ADMIN_TELEGRAM_ID}")])
    if not _is_active(update):
        rows.append([InlineKeyboardButton(f"💎 {t(lang, 'activate')}", callback_data="screen:activate")])
    return _keyboard(update, rows)


def _screen(update: Update, terminal: str, context_text: str | None = None) -> str:
    lang = _lang(update)
    body = render_terminal_box(terminal, max_width=40)
    text = f"{render_header(update.effective_user, lang)}\n\n<pre>{body}</pre>"
    if context_text:
        text += f"\n\n{context_text}"
    return text


def _error_screen(update: Update) -> str:
    lang = _lang(update)
    return _screen(update, "[ ERROR ]\nPermintaan timeout.\nServer tidak merespons.", f">> {t(lang, 'try_again')}")


async def render_home(update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool = True) -> None:
    if update.effective_user is None:
        return
    active = _is_active(update)
    terminal = "\n".join(["[ SYSTEM ]: INITIALIZING...", "[ STATUS ]: SYNCING GLOBAL BULLION RESERVES...", "[ ACCESS ]: GRANTED // WELCOME OPERATOR" if active else "[ ACCESS ]: PENDING // CLEARANCE REQUIRED"])
    await _present(update, _screen(update, terminal, f">> {t(_lang(update), 'select_module')}"), home_keyboard(update), edit=edit)


async def render_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return
    if not _is_active(update):
        await render_locked(update, "price")
        return
    try:
        await _answer_loading(update)
        data = await asyncio.wait_for(api_handler.get_cached_or_fresh_price(user.id), timeout=10.0)
        bid = float(data["bid"]); ask = float(data["ask"]); mid = (bid + ask) / 2
        terminal = "\n".join(["[ MARKET PULSE ]", f"PRICE  : {_money(mid)}", f"BID    : {_money(bid)}", f"ASK    : {_money(ask)}", f"HIGH   : {_money(float(data['high']))}", f"LOW    : {_money(float(data['low']))}", f"SOURCE : {_esc(data.get('source', '—'))}"])
        await _present(update, _screen(update, terminal, f">> {t(_lang(update), 'live_feed')} // XAU/USD"), price_keyboard(update))
    except Exception:
        logger.exception("Premium price screen failed")
        await _present(update, _error_screen(update), price_keyboard(update))


async def render_signal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return
    if not _is_active(update):
        await render_locked(update, "signal")
        return
    try:
        await _answer_loading(update)
        data = await asyncio.wait_for(api_handler.get_cached_or_fresh_price(user.id), timeout=10.0)
        indicators = api_handler._simulate_technical_indicators(float(data["bid"]), float(data.get("change_percent", 0)))
        signal = api_handler._determine_signal(float(data["bid"]), indicators)
        terminal = "\n".join(["[ NEURAL STRIKES ]", f"SIGNAL : {signal['direction']}", f"ENTRY  : {_money(signal['entry_low'])} - {_money(signal['entry_high'])}", f"TP1    : {_money(signal['tp1']) if signal['tp1'] else '—'}", f"TP2    : {_money(signal['tp2']) if signal['tp2'] else '—'}", f"TP3    : {_money(signal['tp3']) if signal['tp3'] else '—'}", f"STOP   : {_money(signal['sl']) if signal['sl'] else '—'}"])
        await _present(update, _screen(update, terminal, f">> {t(_lang(update), 'neural_signal')} // XAU/USD"), signal_keyboard(update))
    except Exception:
        logger.exception("Signal screen failed")
        await _present(update, _error_screen(update), signal_keyboard(update))


async def render_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return
    if not _is_active(update):
        await render_locked(update, "analysis")
        return
    try:
        await _answer_loading(update)
        data = await asyncio.wait_for(api_handler.get_cached_or_fresh_price(user.id), timeout=10.0)
        indicators = api_handler._simulate_technical_indicators(float(data["bid"]), float(data.get("change_percent", 0)))
        terminal = "\n".join(["[ STRUCTURE MAP ]", f"TREND  : {_esc(str(indicators.get('ema_trend', 'NEUTRAL')).upper())}", f"RSI    : {indicators.get('rsi', '—')}", f"MACD   : {indicators.get('macd_hist', '—')}", f"EMA    : {indicators.get('ema', '—')}", f"ATR    : {indicators.get('atr', '—')}"])
        await _present(update, _screen(update, terminal, f">> {t(_lang(update), 'analysis_title')} // XAU/USD"), analysis_keyboard(update))
    except Exception:
        logger.exception("Analysis screen failed")
        await _present(update, _error_screen(update), analysis_keyboard(update))


async def render_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return
    db_user = database.get_user_by_telegram_id(user.id)
    active = _is_active(update)
    if active and db_user:
        expiry = database.normalize_datetime_utc(db_user.subscription_expiry)
        expiry_text = expiry.strftime("%d %b %Y • %H:%M UTC") if expiry else "—"
        days_left = max(0, (expiry - datetime.now(timezone.utc)).days) if expiry else 0
        terminal = "\n".join(["[ OPERATOR HUB ]", f"TELEGRAM_ID : {user.id}", "CLEARANCE   : PREMIUM AKTIF", f"KEDALUWARSA : {expiry_text}", f"SISA HARI   : {days_left} hari tersisa"])
        context_text = f">> {t(_lang(update), 'account_status')} // {t(_lang(update), 'active')}"
    else:
        terminal = "\n".join(["[ OPERATOR HUB ]", f"TELEGRAM_ID : {user.id}", "CLEARANCE   : NONAKTIF", "STATUS      : Belum ada langganan aktif"])
        context_text = f">> {t(_lang(update), 'account_status')} // {t(_lang(update), 'inactive')}"
    await _present(update, _screen(update, terminal, context_text), account_keyboard(update))


async def render_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await render_activate(update, context)


async def render_activate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _lang(update)
    terminal = "\n".join(["[ ACCESS & PACKAGE ]", t(lang, "select_plan"), f"🟢 {t(lang, 'days7')}", f"🟡 {t(lang, 'days14')}", f"🔵 {t(lang, 'days30')}"])
    await _present(update, _screen(update, terminal, f">> {t(lang, 'select_plan')}"), access_keyboard(update))


async def render_renew(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await render_activate(update, context)


async def render_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _lang(update)
    await _present(update, _screen(update, f"[ OPERATOR HUB ]\n{t(lang, 'history')}", f">> {t(lang, 'history')}"), _keyboard(update))


async def render_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _lang(update)
    terminal = "\n".join(["[ SYSTEM SYNC ]", t(lang, "settings_title"), f"• {t(lang, 'access')}", f"• {t(lang, 'settings')}", f"• {t(lang, 'language')}", f"• {t(lang, 'history')}", f"• {t(lang, 'support')}"])
    rows = [[InlineKeyboardButton(t(lang, "access"), callback_data="screen:activate"), InlineKeyboardButton(t(lang, "settings"), callback_data="screen:settings")], [InlineKeyboardButton(t(lang, "language"), callback_data="settings:language"), InlineKeyboardButton(t(lang, "support"), callback_data="screen:help")], [InlineKeyboardButton(t(lang, "history"), callback_data="screen:history")]]
    if not _is_active(update):
        rows.append([InlineKeyboardButton(f"💎 {t(lang, 'activate')}", callback_data="screen:activate")])
    await _present(update, _screen(update, terminal, f">> {t(lang, 'menu')} // {t(lang, 'settings')}"), _keyboard(update, rows))


async def render_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _lang(update)
    await _present(update, _screen(update, t(lang, "help_body"), f">> {t(lang, 'support')} // FAQ"), support_keyboard(update))


async def render_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _lang(update)
    terminal = "\n".join(["[ SYSTEM SYNC ]", t(lang, "settings_title"), f"{t(lang, 'interface')} : ON", f"{t(lang, 'timezone')} : UTC+7", f"{t(lang, 'language_value')} : {lang.upper()}"])
    await _present(update, _screen(update, terminal, f">> {t(lang, 'settings')} // {t(lang, 'language')}"), settings_keyboard(update))


async def render_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _lang(update)
    terminal = "\n".join(["[ SUPPORT & HELP ]", t(lang, "support_title"), t(lang, "support_need")])
    await _present(update, _screen(update, terminal, f">> {t(lang, 'support')}"), support_keyboard(update))


async def render_locked(update: Update, module: str) -> None:
    lang = _lang(update)
    labels = {"price": "MARKET PULSE", "signal": "NEURAL STRIKES", "analysis": "STRUCTURE MAP"}
    label = labels.get(module, module.upper())
    terminal = "\n".join(["[ ACCESS DENIED ]", "MODUL TERKUNCI", f"{t(lang, 'activate_required')}", f"{label}."])
    await _present(update, _screen(update, terminal, f">> {t(lang, 'access_required')}"), _keyboard(update, [[InlineKeyboardButton(f"💎 {t(lang, 'activate')}", callback_data="screen:activate")]]))


async def _answer_loading(update: Update, text: str | None = None) -> None:
    query = update.callback_query
    if query:
        try:
            await query.answer(t(_lang(update), "loading"), show_alert=False)
        except Exception:
            pass


async def _present(update: Update, text: str, keyboard: InlineKeyboardMarkup, edit: bool = True) -> None:
    query = update.callback_query
    if query and edit:
        try:
            await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=keyboard)
            return
        except BadRequest as exc:
            if "not modified" in str(exc).lower():
                return
        except Exception as exc:
            logger.debug("Could not edit callback message: %s", exc)
    try:
        if query and query.message:
            await query.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
            return
    except Exception as exc:
        logger.debug("Callback reply fallback failed: %s", exc)
    if update.message:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
'''

main_path = ROOT / 'main.py'
s = main_path.read_text(encoding='utf-8')
s = s.replace('from terminal_style import boot, intel_footer, intel_header, pay_guide, panel, render_header, render_terminal_box, stamp', 'from terminal_style import render_header, render_terminal_box')
s = re.sub(r"GOLD = '◆'\nDIVIDER = '━' \* 36\n", "DIVIDER = '─' * 40\n", s, count=1)
start = s.index('def _persistent_nav(update: Update)')
end = s.index('async def start_command(update: Update', start)
s = s[:start] + CANONICAL_SEGMENT + '\n\n' + s[end:]
start = s.index('async def callback_router(update: Update')
end = s.index('async def unknown_command_handler(update: Update', start)
router = r'''async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    data = query.data or ""
    if data == "noop":
        await query.answer(show_alert=True)
        return
    if data == "paid:menu":
        await paid_confirmation(update, context)
        return
    if data == "nav:home":
        await render_home(update, context)
        return
    if data == "screen:account":
        await render_account(update, context)
        return
    if data in {"screen:home", "screen:menu"}:
        await render_menu(update, context)
        return
    if data.startswith("screen:"):
        target = data.split(":", 1)[1]
        routes = {"price": render_price, "signal": render_signal, "analysis": render_analysis, "activate": render_activate, "access": render_activate, "renew": render_renew, "history": render_history, "settings": render_settings, "support": render_support, "help": render_help}
        handler = routes.get(target)
        if handler:
            if target in {"price", "signal", "analysis"}:
                await _answer_loading(update)
            await handler(update, context)
        return
    if data.startswith("refresh:"):
        target = data.split(":", 1)[1]
        routes = {"price": render_price, "signal": render_signal, "analysis": render_analysis}
        handler = routes.get(target)
        if handler:
            await _answer_loading(update)
            await handler(update, context)
        return
    if data.startswith("retry:"):
        target = data.split(":", 1)[1]
        routes = {"price": render_price, "signal": render_signal, "analysis": render_analysis}
        handler = routes.get(target)
        if handler:
            await _answer_loading(update)
            await handler(update, context)
        return
    if data.startswith("lang:"):
        lang = data.split(":", 1)[1]
        if lang not in LANGUAGES:
            lang = "en"
        database.set_user_language(query.from_user.id, lang)
        await query.answer(t(lang, "saved"), show_alert=False)
        await render_menu(update, context)
        return
    if data == "settings:language":
        await query.answer()
        lang = _lang(update)
        terminal = "\n".join(["[ LANGUAGE SELECTOR ]", t(lang, "choose_language"), t(lang, "language_names")])
        await _present(update, _screen(update, terminal, f">> {t(lang, 'language')} // {t(lang, 'language_value')}"), language_keyboard(update))
        return
    if data == "action:token":
        await query.answer()
        context.user_data["awaiting_token"] = True
        lang = _lang(update)
        await query.message.reply_text(f"{t(lang, 'enter_activation')}\n{t(lang, 'token_note')}", parse_mode="HTML", reply_markup=access_keyboard(update))
        return
'''
s = s[:start] + router + '\n\n' + s[end:]
main_path.write_text(s, encoding='utf-8')

term_path = ROOT / 'terminal_style.py'
term = term_path.read_text(encoding='utf-8')
term = term.replace('line("SYSTEM", f"INITIALIZING NEURAL GOLD {NEURAL_VERSION}...")', 'line("SYSTEM", "INITIALIZING...")')
term_path.write_text(term, encoding='utf-8')

i18n = ROOT / 'i18n.py'
si = i18n.read_text(encoding='utf-8')
if '"history":"Transaction History"' not in si:
    si = si.replace('"loading":"Loading...",', '"loading":"Loading...","history":"Transaction History",', 1)
if '"history":"Riwayat Transaksi"' not in si:
    si = si.replace('"loading":"Memuat...",', '"loading":"Memuat...","history":"Riwayat Transaksi",', 1)
i18n.write_text(si, encoding='utf-8')

# Remove this runner before final commit.
Path(__file__).unlink()
print('GROUP 3.3 SOURCE REFACTOR APPLIED')
