"""NEURAL GOLD v3.2 — consolidated Telegram UI layer."""
from __future__ import annotations

import terminal_style as ts
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def _active(update) -> bool:
    import auth
    user = update.effective_user
    return bool(user and auth.verify_token(user.id)[0])


def _days_label(days: int) -> str:
    return {7: "🕐 7 DAYS — TACTICAL TRIAL", 14: "📅 14 DAYS — STRATEGIC ENTRY", 30: "🗓️ 30 DAYS — FULL OPERATIONAL CONTROL"}[days]


def _checkout(update, days: int) -> str:
    import phase2_bot
    return phase2_bot.checkout_link(update.effective_user.id, days)


def home_keyboard(update):
    import main
    lang = main._lang(update)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📈 Market Pulse", callback_data="screen:price"), InlineKeyboardButton("🧠 Neural Strikes", callback_data="screen:signal")],
        [InlineKeyboardButton("📊 Structure Map", callback_data="screen:analysis"), InlineKeyboardButton("👑 Operator Hub", callback_data="screen:account")],
        [InlineKeyboardButton("⚙️ System Sync", callback_data="screen:settings"), InlineKeyboardButton("🌐 Language", callback_data="settings:language")],
        [InlineKeyboardButton("💎 ACCESS & PLANS", callback_data="screen:access")],
        [InlineKeyboardButton("⌂ MENU", callback_data="nav:menu")],
    ])


def access_keyboard(update):
    import main
    import phase2_bot
    lang = main._lang(update)
    telegram_id = update.effective_user.id
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 7 DAYS — TACTICAL TRIAL", url=phase2_bot.checkout_link(telegram_id, 7))],
        [InlineKeyboardButton("🟡 14 DAYS — STRATEGIC ENTRY", url=phase2_bot.checkout_link(telegram_id, 14))],
        [InlineKeyboardButton("🔵 30 DAYS — FULL OPERATIONAL CONTROL", url=phase2_bot.checkout_link(telegram_id, 30))],
        [InlineKeyboardButton(main.t(lang, "activate"), callback_data="action:token"), InlineKeyboardButton(main.t(lang, "paid"), callback_data="paid:menu")],
        [InlineKeyboardButton(main.t(lang, "back"), callback_data="nav:home"), InlineKeyboardButton(main.t(lang, "menu"), callback_data="nav:home")],
    ])


def price_keyboard(update):
    import main
    if _active(update):
        return main._original_price_keyboard(update)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(_days_label(7), url=_checkout(update, 7))],
        [InlineKeyboardButton(_days_label(14), url=_checkout(update, 14))],
        [InlineKeyboardButton(_days_label(30), url=_checkout(update, 30))],
        [InlineKeyboardButton("← BACK", callback_data="screen:access"), InlineKeyboardButton("⌂ MENU", callback_data="nav:home")],
    ])


async def render_access(update, context):
    import main
    active = _active(update)
    if active:
        user = update.effective_user
        db_user = main.database.get_user_by_telegram_id(user.id)
        expiry = main.database.normalize_datetime_utc(db_user.subscription_expiry) if db_user else None
        expiry_text = expiry.strftime("%d %b %Y • %H:%M UTC") if expiry else "—"
        text = (
            "<b>[ CLEARANCE ]: PREMIUM ACCESS NEURAL GOLD v3.2</b>\n"
            f"{ts.stamp()}\n"
            f"{main.DIVIDER}\n\n"
            "[ ACCESS ]: GRANTED. WELCOME, OPERATOR.\n\n"
            f"CLEARANCE: <b>🟢 ACTIVE</b>\n\n"
            f"ACCESS_UNTIL: <code>{expiry_text}</code>\n\n"
            "[ CORE ]: YOUR OPERATOR HUB IS SYNCHRONIZED."
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👑 Operator Hub", callback_data="screen:account")],
            [InlineKeyboardButton("⌂ MENU", callback_data="nav:menu")],
        ])
    else:
        lang = main._lang(update)
        text = (
            "<b>[ CLEARANCE ]: PREMIUM ACCESS NEURAL GOLD v3.2</b>\n"
            f"{ts.stamp()}\n"
            f"{main.DIVIDER}\n\n"
            "[ ACCESS ]: PENDING // OPERATOR NOT YET CONNECTED\n\n"
            "<pre>  ENCRYPTED PREMIUM MODULES:\n"
            "   ▸ Market Pulse (Live XAU/USD)\n"
            "   ▸ Neural Strikes (Signals)\n"
            "   ▸ Structure Map (Analysis)\n"
            "   ▸ Operator Hub (Dashboard)</pre>\n\n"
            f"{main.t(lang, 'market_pitch')}\n\n"
            "<b>>> SELECT PACKAGE ↓</b>\n"
            f"{main.t(lang, 'select_package_hint')}\n\n"
            f"{main.t(lang, 'activation_route')}"
        )
    if not active:
        kb = access_keyboard(update)
    await main._present(update, text, kb)


async def render_price(update, context):
    import main
    if _active(update):
        await main._original_render_price(update, context)
        return
    # Single purchase surface (audit fix: no duplicate package screen)
    await render_access(update, context)


async def render_home(update, context, edit: bool = True):
    import main
    user = update.effective_user
    if user is None:
        return
    lang = main._lang(update)
    text = (
        "<b>NEURAL GOLD v3.2 // OPERATOR CONSOLE</b>\n"
        "\u2501" * 28 + "\n"
        f"OPERATOR: <b>{main._safe_user_name(user)}</b>\n"
        f"{ts.stamp()}\n\n"
        f"{ts.boot(granted=True)}\n\n"
        f"<i>{main.t(lang, 'home_pitch')}</i>\n\n"
        "<b>>> SELECT A MODULE</b>"
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
        await main._present(update, f"<b>[ KEYGEN ]: ACTIVATE TOKEN</b>\n\n>> {main.t(lang, 'enter_activation')}\n<i>{main.t(lang, 'token_note')}</i>", access_keyboard(update))
        return
    if data == "screen:signal" and not auth.verify_token(user.id)[0]:
        await query.answer("🔒 CLEARANCE REQUIRED", show_alert=True)
        await render_access(update, context)
        return
    if data == "screen:analysis" and not auth.verify_token(user.id)[0]:
        await query.answer("🔒 CLEARANCE REQUIRED", show_alert=True)
        await render_access(update, context)
        return

    # Phase-2 retains payment confirmation, language, support, and token
    # service callbacks without taking ownership of the main UI.
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
