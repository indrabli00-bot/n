"""NEURAL GOLD v3.2 — emoji-first premium UI layer.

The Telegram UI uses descriptive emojis for feature identity. Image/SVG
presentation is intentionally disabled so navigation stays compact and clear.
"""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def install() -> None:
    """Install the emoji-first navigation layer after Phase 2 UI setup."""
    import main
    import phase2_bot

    def home_keyboard(update):
        lang = main._lang(update)
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"📈 {main.t(lang, 'price')}", callback_data="screen:price"),
             InlineKeyboardButton(f"🧠 {main.t(lang, 'signal')}", callback_data="screen:signal")],
            [InlineKeyboardButton(f"📊 {main.t(lang, 'analysis')}", callback_data="screen:analysis"),
             InlineKeyboardButton(f"👑 {main.t(lang, 'account')}", callback_data="screen:account")],
            [InlineKeyboardButton(f"💎 {main.t(lang, 'access')}", callback_data="screen:access"),
             InlineKeyboardButton(f"⚙️ {main.t(lang, 'settings')}", callback_data="screen:settings")],
            [InlineKeyboardButton(f"💬 {main.t(lang, 'support')}", callback_data="screen:support")],
            [InlineKeyboardButton(f"← {main.t(lang, 'back')}", callback_data="nav:home"),
             InlineKeyboardButton(f"⌂ {main.t(lang, 'menu')}", callback_data="nav:home")],
        ])

    def _days_label(lang: str, days: int) -> str:
        labels = {
            "vi": {7: "7 NGÀY", 14: "14 NGÀY", 30: "30 NGÀY"},
            "id": {7: "7 HARI", 14: "14 HARI", 30: "30 HARI"},
            "hi": {7: "7 दिन", 14: "14 दिन", 30: "30 दिन"},
            "zh": {7: "7 天", 14: "14 天", 30: "30 天"},
        }
        return labels.get(lang, {7: "7 DAYS", 14: "14 DAYS", 30: "30 DAYS"})[days]

    def access_keyboard(update):
        lang = main._lang(update)
        telegram_id = update.effective_user.id
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🕐 7 DAYS" if lang == "en" else f"🕐 {_days_label(lang, 7)}", url=phase2_bot.checkout_link(telegram_id, 7)),
             InlineKeyboardButton("📅 14 DAYS" if lang == "en" else f"📅 {_days_label(lang, 14)}", url=phase2_bot.checkout_link(telegram_id, 14)),
             InlineKeyboardButton("🗓️ 30 DAYS" if lang == "en" else f"🗓️ {_days_label(lang, 30)}", url=phase2_bot.checkout_link(telegram_id, 30))],
            [InlineKeyboardButton(f"🔑 {main.t(lang, 'activate')}", callback_data="action:token"),
             InlineKeyboardButton(phase2_bot._ui(lang, "paid"), callback_data="paid:menu")],
            [InlineKeyboardButton(f"👑 {main.t(lang, 'account_status')}", callback_data="screen:account")],
            [InlineKeyboardButton(f"← {main.t(lang, 'back')}", callback_data="nav:home"),
             InlineKeyboardButton(f"⌂ {main.t(lang, 'menu')}", callback_data="nav:home")],
        ])

    async def render_access(update, context):
        user = update.effective_user
        active = bool(user and __import__('auth').verify_token(user.id)[0])
        lang = main._lang(update)
        state = main.t(lang, "active") if active else "READY TO ACTIVATE"
        icon = "🟢" if active else "✅"
        text = (
            f"<b>💎 {main.t(lang, 'premium_access')}</b>\n"
            f"<i>NEURAL GOLD MEMBERSHIP</i>\n{main.DIVIDER}\n\n"
            f"<b>{icon} {state}</b>\n\n"
            f"{main.t(lang, 'unlocks')}\n"
            f"📈 Live XAU/USD pricing\n"
            f"🧠 Neural trade signals\n"
            f"📊 Market structure analysis\n"
            f"👑 Private account dashboard\n\n"
            f"<b>ACCESS PACKAGES</b>\n"
            f"🕐 7 DAYS   •   SHORT TERM\n"
            f"📅 14 DAYS  •   STANDARD\n"
            f"🗓️ 30 DAYS  •   PREMIUM\n\n"
            f"<i>Enter your single-use activation token after purchase.</i>"
        )
        await main._present(update, text, access_keyboard(update))

    main.home_keyboard = home_keyboard
    main.access_keyboard = access_keyboard
    main.render_access = render_access
    phase2_bot.access_keyboard = access_keyboard
    main._emoji_ui_installed = True
