"""NEURAL GOLD v3.2 — command-center UI layer."""
from __future__ import annotations

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
    active = _active(update)
    rows = []
    if not active:
        rows.append([InlineKeyboardButton("🎯 Market Pulse", callback_data="screen:price"), InlineKeyboardButton("⚡️ Neural Strikes", callback_data="screen:signal")])
        rows.append([InlineKeyboardButton("🏗️ Structure Map", callback_data="screen:analysis"), InlineKeyboardButton("♛ Operator Hub", callback_data="screen:account")])
    else:
        rows.append([InlineKeyboardButton("⚡️ Neural Strikes", callback_data="screen:signal"), InlineKeyboardButton("🏗️ Structure Map", callback_data="screen:analysis")])
        rows.append([InlineKeyboardButton("♛ Operator Hub", callback_data="screen:account")])
    rows.extend([
        [InlineKeyboardButton("⚙️ System Sync", callback_data="screen:settings"), InlineKeyboardButton("🌐 Uplink", callback_data="screen:support")],
        [InlineKeyboardButton("💎 Premium Clearance", callback_data="screen:access")],
        [InlineKeyboardButton("⌂ MENU", callback_data="nav:home")],
    ])
    return InlineKeyboardMarkup(rows)


def access_keyboard(update):
    import main
    active = _active(update)
    rows = []
    if not active:
        rows.append([InlineKeyboardButton("🎯 SELECT CLEARANCE", callback_data="screen:price")])
    rows.append([InlineKeyboardButton("🔑 ACTIVATE TOKEN", callback_data="action:token")])
    rows.append([InlineKeyboardButton("♛ OPERATOR HUB", callback_data="screen:account")])
    rows.append([InlineKeyboardButton("🌐 UPLINK", callback_data="screen:support")])
    rows.append([InlineKeyboardButton("⌂ MENU", callback_data="nav:home")])
    return InlineKeyboardMarkup(rows)


def price_keyboard(update):
    import main
    if _active(update):
        return main._original_price_keyboard(update)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(_days_label(7), url=_checkout(update, 7))],
        [InlineKeyboardButton(_days_label(14), url=_checkout(update, 14))],
        [InlineKeyboardButton(_days_label(30), url=_checkout(update, 30))],
        [InlineKeyboardButton("🔑 INPUT ACTIVATION TOKEN", callback_data="action:token")],
        [InlineKeyboardButton("← BACK", callback_data="nav:home"), InlineKeyboardButton("⌂ MENU", callback_data="nav:home")],
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
            "<b>PREMIUM ACCESS</b>\nNEURAL GOLD v3.2\n"
            "-------------------------------------------------\n\n"
            "<b>✓ CLEARANCE ACTIVE</b>\n\n"
            f"Access until <code>{expiry_text}</code>\n\n"
            "Your Alpha Terminal is synchronized."
        )
    else:
        text = (
            "<b>PREMIUM ACCESS</b>\nNEURAL GOLD v3.2\n"
            "-------------------------------------------------\n\n"
            "<i>\"Anda berada di dalam, tapi Anda belum 'terhubung'.</i>\n\n"
            "Pasar XAU/USD adalah mesin pemindah uang dari trader amatir ke institusi. Tanpa akses ke saraf pusat kami, Anda hanyalah statistik dalam data likuiditas mereka.\n\n"
            "<b>Jangan hanya trading. Dominasi.</b>\n\n"
            "Aktifkan enkripsi premium untuk menghentikan penebakan dan mulai melihat struktur pasar yang sebenarnya:\n\n"
            "◈ Institutional Orderflow (Live XAU/USD)\n"
            "◎ Neural Precision Strikes (Signals)\n"
            "⌁ Market Architecture (Structural Analysis)\n"
            "♛ Alpha Terminal (Private Dashboard)\n\n"
            "<b>SELECT YOUR CLEARANCE LEVEL:</b>\n"
            "Pilih MARKET PULSE untuk membuka 7/14/30 hari.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<b>INPUT ACTIVATION TOKEN BELOW TO SYNC.</b>"
        )
    await main._present(update, text, access_keyboard(update))


async def render_price(update, context):
    import main
    if _active(update):
        await main._original_render_price(update, context)
        return
    text = (
        "<b>🎯 MARKET PULSE // CLEARANCE</b>\nNEURAL GOLD v3.2\n"
        f"{main.DIVIDER}\n\n"
        "<i>Clearance levels control the duration of your premium connection.</i>\n\n"
        "<b>SELECT YOUR CLEARANCE LEVEL:</b>\n\n"
        "🕐 <b>7 DAYS — Tactical Trial</b>\n"
        "📅 <b>14 DAYS — Strategic Entry</b>\n"
        "🗓️ <b>30 DAYS — Full Operational Control</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<b>SELECT A CLEARANCE LEVEL TO CONTINUE.</b>"
    )
    await main._present(update, text, price_keyboard(update))


async def render_home(update, context, edit: bool = True):
    import main
    user = update.effective_user
    if user is None:
        return
    active = _active(update)
    if active:
        text = (
            "<b>NEURAL GOLD v3.2 // ALPHA TERMINAL</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Operator: <b>{main._safe_user_name(user)}</b>\n"
            "Status: CLEARANCE GRANTED ✅\n\n"
            "<i>\"Saraf pusat XAU/USD kini tersinkronisasi dengan akun Anda. Seluruh data market telah difilter; hanya presisi yang tersisa.</i>\n\n"
            "Gunakan modul di bawah untuk mendominasi aliran harga.\n\n"
            "<b>S E L E C T _ M O D U L E</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚡️ Neural Strikes (Signals)\n"
            "🏗️ Structure Map (Structural Analysis)\n"
            "♛ Operator Hub (Private Dashboard)\n"
            "⚙️ System Sync (Settings)\n"
            "🌐 Uplink (Support)"
        )
    else:
        text = (
            "<b>NEURAL GOLD v3.2 // ALPHA TERMINAL</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Operator: <b>{main._safe_user_name(user)}</b>\n"
            "Status: CLEARANCE PENDING ⏳\n\n"
            "<i>Market intelligence is visible. Premium signal layers remain encrypted until clearance is activated.</i>\n\n"
            "<b>S E L E C T _ M O D U L E</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🎯 Market Pulse (Clearance Levels)\n"
            "⚡️ Neural Strikes (Locked)\n"
            "🏗️ Structure Map (Locked)\n"
            "♛ Operator Hub (Private Dashboard)\n"
            "⚙️ System Sync (Settings)\n"
            "🌐 Uplink (Support)"
        )
    await main._present(update, text, home_keyboard(update), edit=edit)


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
    main._emoji_ui_installed = True
