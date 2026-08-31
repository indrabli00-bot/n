"""NEURAL GOLD v3.3 — consolidated Telegram UI ownership layer."""
from __future__ import annotations

import terminal_style as ts
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def _active(update) -> bool:
    import auth
    user = update.effective_user
    return bool(user and auth.verify_token(user.id)[0])


def _lang(update) -> str:
    import main
    return main._lang(update)


def _t(update, key: str) -> str:
    import main
    return main.t(_lang(update), key)


def _days_label(update, days: int) -> str:
    return _t(update, {7: "days7", 14: "days14", 30: "days30"}[days])


def _checkout(update, days: int) -> str:
    import phase2_bot
    return phase2_bot.checkout_link(update.effective_user.id, days)


def _persistent_nav(update) -> list[InlineKeyboardButton]:
    lang = _lang(update)
    return [
        InlineKeyboardButton(f"🏠 {_t(update, 'menu')}", callback_data="nav:home"),
        InlineKeyboardButton(f"👨‍💼 {_t(update, 'account')}", callback_data="screen:account"),
    ]


def _keyboard(update, rows: list[list[InlineKeyboardButton]] | None = None) -> InlineKeyboardMarkup:
    keyboard = list(rows or [])
    keyboard.append(_persistent_nav(update))
    return InlineKeyboardMarkup(keyboard)


def home_keyboard(update):
    return _keyboard(update, [
        [InlineKeyboardButton(f"📈 {_t(update, 'price')}", callback_data="screen:price"), InlineKeyboardButton(f"🧠 {_t(update, 'signal')}", callback_data="screen:signal")],
        [InlineKeyboardButton(f"📊 {_t(update, 'analysis')}", callback_data="screen:analysis"), InlineKeyboardButton(f"👑 {_t(update, 'account')}", callback_data="screen:account")],
        [InlineKeyboardButton(f"⚙️ {_t(update, 'settings')}", callback_data="screen:settings"), InlineKeyboardButton(f"🌐 {_t(update, 'language')}", callback_data="settings:language")],
        [InlineKeyboardButton(f"💎 {_t(update, 'access')}", callback_data="screen:access")],
    ])


def access_keyboard(update):
    import phase2_bot
    telegram_id = update.effective_user.id
    return _keyboard(update, [
        [InlineKeyboardButton(f"🟢 {_days_label(update, 7)}", url=phase2_bot.checkout_link(telegram_id, 7))],
        [InlineKeyboardButton(f"🟡 {_days_label(update, 14)}", url=phase2_bot.checkout_link(telegram_id, 14))],
        [InlineKeyboardButton(f"🔵 {_days_label(update, 30)}", url=phase2_bot.checkout_link(telegram_id, 30))],
        [InlineKeyboardButton(_t(update, "activate"), callback_data="action:token"), InlineKeyboardButton(_t(update, "paid"), callback_data="paid:menu")],
    ])


def price_keyboard(update):
    import main
    if _active(update):
        return _keyboard(update, [[InlineKeyboardButton(_t(update, "refresh"), callback_data="screen:price")]])
    return _keyboard(update, [
        [InlineKeyboardButton(f"🟢 {_days_label(update, 7)}", url=_checkout(update, 7))],
        [InlineKeyboardButton(f"🟡 {_days_label(update, 14)}", url=_checkout(update, 14))],
        [InlineKeyboardButton(f"🔵 {_days_label(update, 30)}", url=_checkout(update, 30))],
    ])


def signal_keyboard(update):
    return _keyboard(update, [[InlineKeyboardButton(_t(update, "new_signal"), callback_data="screen:signal")]])


def analysis_keyboard(update):
    return _keyboard(update, [[InlineKeyboardButton(_t(update, "refresh_analysis"), callback_data="screen:analysis")]])


def account_keyboard(update):
    return _keyboard(update, [[InlineKeyboardButton(_t(update, "refresh_status"), callback_data="screen:account")]])


def settings_keyboard(update):
    return _keyboard(update, [
        [InlineKeyboardButton(_t(update, "interface"), callback_data="noop")],
        [InlineKeyboardButton(_t(update, "timezone"), callback_data="noop")],
        [InlineKeyboardButton(_t(update, "data_mode"), callback_data="noop")],
    ])


def language_keyboard(update):
    import main
    rows = [[InlineKeyboardButton(label, callback_data=data)] for label, data in main.language_buttons()]
    return _keyboard(update, rows)


def support_keyboard(update):
    import main
    rows = []
    if main.ADMIN_TELEGRAM_ID:
        rows.append([InlineKeyboardButton(_t(update, "contact"), url=f"tg://user?id={main.ADMIN_TELEGRAM_ID}")])
    return _keyboard(update, rows)


def _pending_modules(update) -> str:
    return "\n".join([
        f"  {_t(update, 'price')} — XAU/USD",
        f"  {_t(update, 'signal')}",
        f"  {_t(update, 'analysis')}",
        f"  {_t(update, 'account')}",
    ])


async def render_access(update, context):
    import main
    active = _active(update)
    lang = _lang(update)
    if active:
        user = update.effective_user
        db_user = main.database.get_user_by_telegram_id(user.id)
        expiry = main.database.normalize_datetime_utc(db_user.subscription_expiry) if db_user else None
        expiry_text = expiry.strftime("%d %b %Y • %H:%M UTC") if expiry else "—"
        content = (
            f"[ CLEARANCE ]: NEURAL GOLD v3.2\n{ts.stamp()}\n"
            f"[ ACCESS ]: {main.t(lang, 'premium_active')}\n"
            f"CLEARANCE: 🟢 {main.t(lang, 'active')}\n"
            f"{main.t(lang, 'access_until').upper()}: {expiry_text}\n"
            f"[ CORE ]: {main.t(lang, 'home_pitch')}"
        )
        text = f"<pre>{ts.render_terminal_box(content)}</pre>"
    else:
        content = (
            f"[ CLEARANCE ]: NEURAL GOLD v3.2\n{ts.stamp()}\n"
            "[ ACCESS ]: PENDING // OPERATOR NOT YET CONNECTED\n\n"
            f"{_pending_modules(update)}\n\n"
            f">> {main.t(lang, 'access')}\n"
            f"{main.t(lang, 'days7')}\n{main.t(lang, 'days14')}\n{main.t(lang, 'days30')}"
        )
        text = f"<pre>{ts.render_terminal_box(content)}</pre>"
    await main._present(update, text, access_keyboard(update))


async def render_price(update, context):
    import main
    if _active(update):
        await main._original_render_price(update, context)
        return
    await render_access(update, context)


async def render_home(update, context, edit: bool = True):
    import main
    user = update.effective_user
    if user is None:
        return
    granted = _active(update)
    lang = _lang(update)
    content = (
        f"NEURAL GOLD v3.2 // OPERATOR CONSOLE\n{ts.stamp()}\n"
        f"OPERATOR: {main._safe_user_name(user)}\n"
        f"{ts.boot(granted=granted)}\n"
        f"{main.t(lang, 'premium_active') if granted else '[ ACCESS ]: PENDING // CLEARANCE REQUIRED'}\n"
        f"{main.t(lang, 'home_pitch')}\n\n"
        f">> {main.t(lang, 'select_module')}"
    )
    text = f"<pre>{ts.render_terminal_box(content)}</pre>"
    await main._present(update, text, home_keyboard(update), edit=edit)


async def callback_router(update, context):
    import main
    import auth
    import phase2_bot
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    data = query.data or ""
    if data in {"nav:home", "screen:home"}:
        await query.answer()
        await render_home(update, context)
        return
    if data in {"nav:menu", "screen:menu"}:
        await query.answer()
        await main.render_menu(update, context)
        return
    if data == "screen:access":
        await query.answer()
        await render_access(update, context)
        return
    if data == "screen:price":
        await query.answer()
        await render_price(update, context)
        return
    if data == "screen:help":
        await query.answer()
        await main.render_help(update, context)
        return
    if data == "action:token":
        await query.answer()
        context.user_data["awaiting_token"] = True
        await main._present(
            update,
            f"<pre>{ts.render_terminal_box(f'[ KEYGEN ]: {_t(update, 'activate')}\\n\\n>> {_t(update, 'enter_activation')}\\n{_t(update, 'token_note')}')}</pre>",
            access_keyboard(update),
        )
        return
    if data == "screen:signal" and not auth.verify_token(user.id)[0]:
        await query.answer(f"🔒 {_t(update, 'access_required')}", show_alert=True)
        await render_access(update, context)
        return
    if data == "screen:analysis" and not auth.verify_token(user.id)[0]:
        await query.answer(f"🔒 {_t(update, 'access_required')}", show_alert=True)
        await render_access(update, context)
        return
    await phase2_bot._callback_router(update, context)


async def unknown_text_handler(update, context):
    import phase2_bot
    await phase2_bot._unknown_text_handler(update, context)


def install() -> None:
    import main
    main.home_keyboard = home_keyboard
    main.access_keyboard = access_keyboard
    main.price_keyboard = price_keyboard
    main.signal_keyboard = signal_keyboard
    main.analysis_keyboard = analysis_keyboard
    main.account_keyboard = account_keyboard
    main.settings_keyboard = settings_keyboard
    main.language_keyboard = language_keyboard
    main.support_keyboard = support_keyboard
    main.render_access = render_access
    main.render_price = render_price
    main.render_home = render_home
    main.callback_router = callback_router
    main.unknown_text_handler = unknown_text_handler
    main._emoji_ui_installed = True
