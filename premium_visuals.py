"""NEURAL GOLD v3.2 — consolidated Telegram UI layer."""
from __future__ import annotations

import terminal_style as ts
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def _active(update) -> bool:
    import auth
    user = update.effective_user
    return bool(user and auth.verify_token(user.id)[0])


def _days_label(update, days: int) -> str:
    import main
    lang = main._lang(update)
    key = {7: "days7", 14: "days14", 30: "days30"}[days]
    return main.t(lang, key)


def _checkout(update, days: int) -> str:
    import phase2_bot
    return phase2_bot.checkout_link(update.effective_user.id, days)


def home_keyboard(update):
    import main
    lang = main._lang(update)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📈 {main.t(lang, 'price')}", callback_data="screen:price"), InlineKeyboardButton(f"🧠 {main.t(lang, 'signal')}", callback_data="screen:signal")],
        [InlineKeyboardButton(f"📊 {main.t(lang, 'analysis')}", callback_data="screen:analysis"), InlineKeyboardButton(f"👑 {main.t(lang, 'account')}", callback_data="screen:account")],
        [InlineKeyboardButton(f"⚙️ {main.t(lang, 'settings')}", callback_data="screen:settings"), InlineKeyboardButton(f"🌐 {main.t(lang, 'language')}", callback_data="settings:language")],
        [InlineKeyboardButton(f"💎 {main.t(lang, 'access')}", callback_data="screen:access")],
        [InlineKeyboardButton(main.t(lang, "menu"), callback_data="nav:menu")],
    ])


def access_keyboard(update):
    import main
    import phase2_bot
    lang = main._lang(update)
    telegram_id = update.effective_user.id
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🟢 {_days_label(update, 7)}", url=phase2_bot.checkout_link(telegram_id, 7))],
        [InlineKeyboardButton(f"🟡 {_days_label(update, 14)}", url=phase2_bot.checkout_link(telegram_id, 14))],
        [InlineKeyboardButton(f"🔵 {_days_label(update, 30)}", url=phase2_bot.checkout_link(telegram_id, 30))],
        [InlineKeyboardButton(main.t(lang, "activate"), callback_data="action:token"), InlineKeyboardButton(main.t(lang, "paid"), callback_data="paid:menu")],
        [InlineKeyboardButton(main.t(lang, "back"), callback_data="nav:home"), InlineKeyboardButton(main.t(lang, "menu"), callback_data="nav:home")],
    ])


def price_keyboard(update):
    import main
    if _active(update):
        return main._original_price_keyboard(update)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🟢 {_days_label(update, 7)}", url=_checkout(update, 7))],
        [InlineKeyboardButton(f"🟡 {_days_label(update, 14)}", url=_checkout(update, 14))],
        [InlineKeyboardButton(f"🔵 {_days_label(update, 30)}", url=_checkout(update, 30))],
        [InlineKeyboardButton(main.t(main._lang(update), "back"), callback_data="screen:access"), InlineKeyboardButton(main.t(main._lang(update), "menu"), callback_data="nav:home")],
    ])


async def render_access(update, context):
    import main
    lang = main._lang(update)
    active = _active(update)
    if active:
        user = update.effective_user
        db_user = main.database.get_user_by_telegram_id(user.id)
        expiry = main.database.normalize_datetime_utc(db_user.subscription_expiry) if db_user else None
        expiry_text = expiry.strftime("%d %b %Y • %H:%M UTC") if expiry else "—"
        text = (
            "<b>[ CLEARANCE ]: NEURAL GOLD v3.2</b>\n"
            f"{ts.stamp()}\n"
            f"{main.DIVIDER}\n\n"
            f"[ ACCESS ]: GRANTED. {main.t(lang, 'welcome').upper() if lang == 'id' else 'WELCOME, OPERATOR.'}\n\n"
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
            f"<pre>  {main.t(lang, 'price')} — XAU/USD\n"
            f"  {main.t(lang, 'signal')} — Neural Signal\n"
            f"  {main.t(lang, 'analysis')} — {main.t(lang, 'analysis')}\n"
            f"  {main.t(lang, 'account')} — {main.t(lang, 'account')}</pre>\n\n"
            f"{main.t(lang, 'market_pitch')}\n\n"
            f"<b>>> {main.t(lang, 'select_plan').upper()}</b>\n"
            f"{main.t(lang, 'select_package_hint')}"
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
    lang = main._lang(update)
    granted = _active(update)
    pitch = main.t(lang, "home_pitch") if granted else main.t(lang, "market_pitch")
    status = main.t(lang, "premium_active") if granted else "[ ACCESS ]: PENDING // CLEARANCE REQUIRED"
    text = (
        "<b>NEURAL GOLD v3.2 // OPERATOR CONSOLE</b>\n"
        f"{'━' * 28}\n"
        f"OPERATOR: <b>{main._safe_user_name(user)}</b>\n"
        f"{ts.stamp()}\n\n"
        f"{ts.boot(granted=granted)}\n"
        f"{status}\n\n"
        f"<i>{pitch}</i>\n\n"
        f"<b>>> {main.t(lang, 'select_module')}</b>"
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
    if data == "nav:access" or data == "screen:access":
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
        lang = main._lang(update)
        await main._present(update, f"<b>[ KEYGEN ]: {main.t(lang, 'activate')}</b>\n\n>> {main.t(lang, 'enter_activation')}\n<i>{main.t(lang, 'token_note')}</i>", access_keyboard(update))
        return
    if data == "screen:signal" and not auth.verify_token(user.id)[0]:
        await query.answer(f"🔒 {main.t(main._lang(update), 'access_required')}", show_alert=True)
        await render_access(update, context)
        return
    if data == "screen:analysis" and not auth.verify_token(user.id)[0]:
        await query.answer(f"🔒 {main.t(main._lang(update), 'access_required')}", show_alert=True)
        await render_access(update, context)
        return

    # Phase-2 retains payment confirmation, language, support, and token service callbacks.
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
