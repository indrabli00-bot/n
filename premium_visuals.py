"""NEURAL GOLD v3.2 — consolidated Telegram UI layer."""
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
    key = {7: "days7", 14: "days14", 30: "days30"}[days]
    return _t(update, key)


def _checkout(update, days: int) -> str:
    import phase2_bot
    return phase2_bot.checkout_link(update.effective_user.id, days)


def _pending_modules(update) -> str:
    return "\n".join([
        f"  { _t(update, 'price') } — XAU/USD",
        f"  { _t(update, 'signal') }",
        f"  { _t(update, 'analysis') }",
        f"  { _t(update, 'account') }",
    ])


def home_keyboard(update):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📈 {_t(update, 'price')}", callback_data="screen:price"), InlineKeyboardButton(f"🧠 {_t(update, 'signal')}", callback_data="screen:signal")],
        [InlineKeyboardButton(f"📊 {_t(update, 'analysis')}", callback_data="screen:analysis"), InlineKeyboardButton(f"👑 {_t(update, 'account')}", callback_data="screen:account")],
        [InlineKeyboardButton(f"⚙️ {_t(update, 'settings')}", callback_data="screen:settings"), InlineKeyboardButton(f"🌐 {_t(update, 'language')}", callback_data="settings:language")],
        [InlineKeyboardButton(f"💎 {_t(update, 'access')}", callback_data="screen:access")],
        [InlineKeyboardButton(_t(update, "menu"), callback_data="nav:menu")],
    ])


def access_keyboard(update):
    import phase2_bot
    telegram_id = update.effective_user.id
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🟢 {_days_label(update, 7)}", url=phase2_bot.checkout_link(telegram_id, 7))],
        [InlineKeyboardButton(f"🟡 {_days_label(update, 14)}", url=phase2_bot.checkout_link(telegram_id, 14))],
        [InlineKeyboardButton(f"🔵 {_days_label(update, 30)}", url=phase2_bot.checkout_link(telegram_id, 30))],
        [InlineKeyboardButton(_t(update, "activate"), callback_data="action:token"), InlineKeyboardButton(_t(update, "paid"), callback_data="paid:menu")],
        [InlineKeyboardButton(_t(update, "back"), callback_data="nav:home"), InlineKeyboardButton(_t(update, "menu"), callback_data="nav:home")],
    ])


def price_keyboard(update):
    import main
    if _active(update):
        return main._original_price_keyboard(update)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🟢 {_days_label(update, 7)}", url=_checkout(update, 7))],
        [InlineKeyboardButton(f"🟡 {_days_label(update, 14)}", url=_checkout(update, 14))],
        [InlineKeyboardButton(f"🔵 {_days_label(update, 30)}", url=_checkout(update, 30))],
        [InlineKeyboardButton(_t(update, "back"), callback_data="screen:access"), InlineKeyboardButton(_t(update, "menu"), callback_data="nav:home")],
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
        text = (
            "<b>[ CLEARANCE ]: NEURAL GOLD v3.2</b>\n"
            f"{ts.stamp()}\n"
            f"{main.DIVIDER}\n\n"
            f"[ ACCESS ]: {main.t(lang, 'premium_active')}\n\n"
            f"CLEARANCE: <b>🟢 {main.t(lang, 'active')}</b>\n\n"
            f"{main.t(lang, 'access_until').upper()}: <code>{expiry_text}</code>\n\n"
            f"[ CORE ]: {main.t(lang, 'home_pitch')}"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"👑 {main.t(lang, 'account')}", callback_data="screen:account")],
            [InlineKeyboardButton(main.t(lang, "menu"), callback_data="nav:menu")],
        ])
    else:
        text = (
            "<b>[ CLEARANCE ]: NEURAL GOLD v3.2</b>\n"
            f"{ts.stamp()}\n"
            f"{main.DIVIDER}\n\n"
            "[ ACCESS ]: PENDING // OPERATOR NOT YET CONNECTED\n\n"
            f"<pre>{_pending_modules(update)}</pre>\n\n"
            f"<b>>> {main.t(lang, 'access')}</b>\n"
            f"{main.t(lang, 'days7')}\n"
            f"{main.t(lang, 'days14')}\n"
            f"{main.t(lang, 'days30')}"
        )
        kb = access_keyboard(update)
    await main._present(update, text, kb)


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
    text = (
        "<b>NEURAL GOLD v3.2 // OPERATOR CONSOLE</b>\n"
        f"{'━' * 28}\n"
        f"OPERATOR: <b>{main._safe_user_name(user)}</b>\n"
        f"{ts.stamp()}\n\n"
        f"{ts.boot(granted=granted)}\n"
        f"{main.t(main._lang(update), 'premium_active') if granted else '[ ACCESS ]: PENDING // CLEARANCE REQUIRED'}\n\n"
        f"<i>{main.t(main._lang(update), 'home_pitch')}</i>\n\n"
        f"<b>>> {main.t(main._lang(update), 'select_module')}</b>"
    )
    await main._present(update, text, home_keyboard(update), edit=edit)


async def callback_router(update, context):
    """Single UI owner; delegate only legacy Phase-2 service callbacks."""
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
    if data == "nav:menu":
        await query.answer()
        await main.render_menu(update, context)
        return
    if data in {"nav:access", "screen:access"}:
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
        await main._present(update, f"<b>[ KEYGEN ]: {_t(update, 'activate')}</b>\n\n>> {_t(update, 'enter_activation')}\n<i>{_t(update, 'token_note')}</i>", access_keyboard(update))
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
    if getattr(main, "_original_render_price", None) is None:
        main._original_render_price = main.render_price
    if getattr(main, "_original_price_keyboard", None) is None:
        main._original_price_keyboard = main.price_keyboard
    main.home_keyboard = home_keyboard
    main.access_keyboard = access_keyboard
    main.price_keyboard = price_keyboard
    main.render_access = render_access
    main.render_price = render_price
    main.render_home = render_home
    main.callback_router = callback_router
    main.unknown_text_handler = unknown_text_handler
    main._emoji_ui_installed = True
