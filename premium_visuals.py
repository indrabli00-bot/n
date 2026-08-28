"""NEURAL GOLD v3.2 — emoji-first premium UI layer.

The Telegram UI uses descriptive emojis for feature identity. Image/SVG
presentation is intentionally disabled so navigation stays compact and clear.
"""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def _label(text: str) -> str:
    """Remove legacy decorative prefixes before applying the new feature icon."""
    prefixes = ("🟢 ", "🟡 ", "🔵 ", "♛ ", "◆ ", "◉ ", "◈ ", "⌁ ", "↻ ", "● ", "○ ", "🔑 ")
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if text.startswith(prefix):
                text = text[len(prefix):]
                changed = True
    return text


def install() -> None:
    """Install the emoji-first navigation layer after Phase 2 UI setup."""
    import main
    import phase2_bot
    import auth

    def home_keyboard(update):
        lang = main._lang(update)
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"📈 {_label(main.t(lang, 'price'))}", callback_data="screen:price"),
             InlineKeyboardButton(f"🧠 {_label(main.t(lang, 'signal'))}", callback_data="screen:signal")],
            [InlineKeyboardButton(f"📊 {_label(main.t(lang, 'analysis'))}", callback_data="screen:analysis"),
             InlineKeyboardButton(f"👑 {_label(main.t(lang, 'account'))}", callback_data="screen:account")],
            [InlineKeyboardButton(f"💎 {_label(main.t(lang, 'access'))}", callback_data="screen:access"),
             InlineKeyboardButton(f"⚙️ {_label(main.t(lang, 'settings'))}", callback_data="screen:settings")],
            [InlineKeyboardButton(f"💬 {_label(main.t(lang, 'support'))}", callback_data="screen:support")],
            [InlineKeyboardButton(main.t(lang, 'back'), callback_data="nav:home"),
             InlineKeyboardButton(main.t(lang, 'menu'), callback_data="nav:home")],
        ])

    def _days_label(lang: str, days: int) -> str:
        keys = {7: "days7", 14: "days14", 30: "days30"}
        return _label(main.t(lang, keys[days]))

    def access_keyboard(update):
        lang = main._lang(update)
        telegram_id = update.effective_user.id
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🕐 {_days_label(lang, 7)}", url=phase2_bot.checkout_link(telegram_id, 7)),
             InlineKeyboardButton(f"📅 {_days_label(lang, 14)}", url=phase2_bot.checkout_link(telegram_id, 14)),
             InlineKeyboardButton(f"🗓️ {_days_label(lang, 30)}", url=phase2_bot.checkout_link(telegram_id, 30))],
            [InlineKeyboardButton(f"🔑 {_label(main.t(lang, 'activate'))}", callback_data="action:token"),
             InlineKeyboardButton(phase2_bot._ui(lang, "paid"), callback_data="paid:menu")],
            [InlineKeyboardButton(f"👑 {_label(main.t(lang, 'account_status'))}", callback_data="screen:account")],
            [InlineKeyboardButton(main.t(lang, 'back'), callback_data="nav:home"),
             InlineKeyboardButton(main.t(lang, 'menu'), callback_data="nav:home")],
        ])

    async def render_access(update, context):
        user = update.effective_user
        active = bool(user and auth.verify_token(user.id)[0])
        lang = main._lang(update)
        state = _label(main.t(lang, "active")) if active else _label(main.t(lang, "ready"))
        icon = "🟢" if active else "✅"
        text = (
            f"<b>💎 {_label(main.t(lang, 'premium_access'))}</b>\n"
            f"<i>{main.t(lang, 'membership')}</i>\n{main.DIVIDER}\n\n"
            f"<b>{icon} {state}</b>\n\n"
            f"{main.t(lang, 'unlocks')}\n"
            f"📈 {_label(main.t(lang, 'live_price'))}\n"
            f"🧠 {_label(main.t(lang, 'neural_signal'))}\n"
            f"📊 {_label(main.t(lang, 'market_analysis'))}\n"
            f"👑 {_label(main.t(lang, 'account'))}\n\n"
            f"<b>💎 {_label(main.t(lang, 'access'))}</b>\n"
            f"🕐 {_label(main.t(lang, 'days7'))}\n"
            f"📅 {_label(main.t(lang, 'days14'))}\n"
            f"🗓️ {_label(main.t(lang, 'days30'))}\n\n"
            f"<i>{main.t(lang, 'enter_token')}</i>"
        )
        await main._present(update, text, access_keyboard(update))

    main.home_keyboard = home_keyboard
    main.access_keyboard = access_keyboard
    main.render_access = render_access
    phase2_bot.access_keyboard = access_keyboard
    main._emoji_ui_installed = True
