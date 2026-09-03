from __future__ import annotations

import logging
from typing import Callable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update

from i18n import detect_language, t
import auth
import main
import terminal_style

logger = logging.getLogger(__name__)

PANEL_WIDTH = 42


def _lang(update: Update) -> str:
    user = update.effective_user
    return detect_language(user.language_code if user else None)


def _active(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False
    try:
        return bool(auth.verify_token(user.id)[0])
    except Exception:
        logger.exception("Failed to verify token for UI state")
        return False


def _button_text(text: str, max_width: int | None = None) -> str:
    return terminal_style.word_wrap(text, max_width or PANEL_WIDTH)[0]


def _nav(update: Update) -> list[list[InlineKeyboardButton]]:
    lang = _lang(update)
    menu = t(lang, "menu").removeprefix("⌂ ").strip().title()
    account = t(lang, "account").strip().title()
    return [[
        InlineKeyboardButton(_button_text(f"🏠 {menu}"), callback_data="nav:home"),
        InlineKeyboardButton(_button_text(f"👨‍💼 {account}"), callback_data="screen:account"),
    ]]


def _keyboard(update: Update, rows: list[list[InlineKeyboardButton]] | None = None) -> InlineKeyboardMarkup:
    # `_nav()` normally returns a list, but the production app replaces it
    # with Telegram's `inline_keyboard`, which is tuple-shaped. Normalize
    # both outer and inner sequences before concatenation.
    nav_rows = [list(row) for row in _nav(update)]
    return InlineKeyboardMarkup(list(rows or []) + nav_rows)


def _header(update: Update, screen: str) -> str:
    user = update.effective_user
    active = _active(update)
    operator = f"@{user.username}" if user and user.username else (user.first_name if user else "OPERATOR")
    status_key = "active" if active else "inactive"
    status_icon = "🟢" if active else "🔴"
    status = t(_lang(update), status_key)
    return f"NEURAL GOLD {main.NEURAL_VERSION}\nOPERATOR : {operator}\nSTATUS   : {status[:1].upper() + status[1:]} {status_icon}\n\n[ {screen.upper()} ]"


def _screen(update: Update, screen: str, terminal: str, footer: str, keyboard: InlineKeyboardMarkup) -> tuple[str, InlineKeyboardMarkup]:
    return f"{_header(update, screen)}\n\n<pre>{terminal_style.render_terminal_box(terminal)}</pre>\n\n>> {t(_lang(update), 'select_module')}\n{footer}", keyboard


def _module_rows(update: Update) -> list[list[InlineKeyboardButton]]:
    lang = _lang(update)
    return [
        [InlineKeyboardButton(_button_text(t(lang, "market_pulse")), callback_data="screen:price"), InlineKeyboardButton(_button_text(t(lang, "neural_strikes")), callback_data="screen:signal")],
        [InlineKeyboardButton(_button_text(t(lang, "structure_map")), callback_data="screen:analysis")],
    ]


def _locked_module_rows(update: Update) -> list[list[InlineKeyboardButton]]:
    lang = _lang(update)
    return [
        [InlineKeyboardButton(_button_text(f"🔒 {t(lang, 'market_pulse')}"), callback_data="screen:price"), InlineKeyboardButton(_button_text(f"🔒 {t(lang, 'neural_strikes')}"), callback_data="screen:signal")],
        [InlineKeyboardButton(_button_text(f"🔒 {t(lang, 'structure_map')}"), callback_data="screen:analysis")],
        [InlineKeyboardButton(_button_text(f"💎 {t(lang, 'activate_premium')}"), callback_data="screen:activate")],
    ]


def _access_keyboard(update: Update, module: str | None = None) -> InlineKeyboardMarkup:
    import phase2_bot
    tid = update.effective_user.id
    rows = [[
        InlineKeyboardButton(_button_text(f"🟢 {t(_lang(update), 'days7')}"), url=phase2_bot.checkout_link(tid, 7)),
        InlineKeyboardButton(_button_text(f"🟡 {t(_lang(update), 'days14')}"), url=phase2_bot.checkout_link(tid, 14)),
    ], [InlineKeyboardButton(_button_text(f"🔵 {t(_lang(update), 'days30')}", PANEL_WIDTH), url=phase2_bot.checkout_link(tid, 30))]]
    return _keyboard(update, rows)


async def render_home(update: Update, context, edit: bool = True) -> None:
    active = _active(update)
    terminal = "\n".join(["[ SYSTEM ]: INITIALIZING...", "[ STATUS ]: SYNCING GLOBAL BULLION RESERVES...", "[ ACCESS ]: GRANTED // WELCOME OPERATOR" if active else "[ ACCESS ]: PENDING // CLEARANCE REQUIRED"])
    rows = _module_rows(update) if active else _locked_module_rows(update)
    text, keyboard = _screen(update, "Home", terminal, "HOME // Select module", _keyboard(update, rows))
    await _present(update, text, keyboard, edit=edit)


async def render_menu(update: Update, context) -> None:
    rows = [
        [InlineKeyboardButton(_button_text("MARKET PULSE"), callback_data="screen:price"), InlineKeyboardButton(_button_text("NEURAL STRIKES"), callback_data="screen:signal")],
        [InlineKeyboardButton(_button_text("STRUCTURE MAP"), callback_data="screen:analysis")],
        [InlineKeyboardButton(_button_text(f"🌐 {t(_lang(update), 'language')}"), callback_data="settings:language")],
        [InlineKeyboardButton(_button_text(f"❓ {t(_lang(update), 'support')}"), callback_data="screen:help")],
    ]
    terminal = "[ SYSTEM ]: NAVIGATION ONLINE\n[ MODE ]: CUSTOMER CONTROL"
    text, keyboard = _screen(update, "Menu", terminal, "MENU // Select module", _keyboard(update, rows))
    await _present(update, text, keyboard)


async def render_account(update: Update, context) -> None:
    user = update.effective_user
    active = _active(update)
    status = "ACTIVE" if active else "INACTIVE"
    terminal = "\n".join([
        "[ ACCOUNT ]: OPERATOR PROFILE",
        f"[ TELEGRAM ]: {user.id if user else 'UNKNOWN'}",
        f"[ ACCESS ]: {status}",
    ])
    rows = [[InlineKeyboardButton(_button_text(f"💎 {t(_lang(update), 'activate_premium')}"), callback_data="screen:activate")]] if not active else []
    text, keyboard = _screen(update, "Account", terminal, "ACCOUNT // Operator profile", _keyboard(update, rows))
    await _present(update, text, keyboard)


async def render_activate(update: Update, context) -> None:
    terminal = "[ PREMIUM ]: ACCESS ACTIVATION\n[ PLANS ]: 7D / 14D / 30D\n[ CHECKOUT ]: WHOP SECURE CHECKOUT"
    text, keyboard = _screen(update, "Activate", terminal, "ACTIVATE // Select plan", _access_keyboard(update))
    await _present(update, text, keyboard)


async def render_price(update: Update, context) -> None:
    text, keyboard = await main._render_price(update, edit=False, contract=True)
    await _present(update, text, keyboard)


async def render_signal(update: Update, context) -> None:
    text, keyboard = await main._render_signal(update, edit=False, contract=True)
    await _present(update, text, keyboard)


async def render_analysis(update: Update, context) -> None:
    text, keyboard = await main._render_analysis(update, edit=False, contract=True)
    await _present(update, text, keyboard)


async def render_help(update: Update, context) -> None:
    lang = _lang(update)
    terminal = "\n".join([
        "[ SUPPORT ]: NEURAL GOLD",
        "[ STATUS ]: ONLINE",
        f"[ LANGUAGE ]: {lang.upper()}",
    ])
    text, keyboard = _screen(update, "Help", terminal, "HELP // Support", _keyboard(update, [[InlineKeyboardButton(_button_text(f"🏠 {t(lang, 'menu')}"), callback_data="nav:home")]]))
    await _present(update, text, keyboard)


async def render_language(update: Update, context) -> None:
    lang = _lang(update)
    rows = [
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang:en"), InlineKeyboardButton("🇮🇩 Indonesia", callback_data="lang:id")],
    ]
    text, keyboard = _screen(update, "Language", "[ SETTINGS ]: LANGUAGE\n[ MODE ]: LOCALIZED UI", "LANGUAGE // Select language", _keyboard(update, rows))
    await _present(update, text, keyboard)


async def _present(update: Update, text: str, keyboard: InlineKeyboardMarkup, edit: bool = True) -> None:
    if update.callback_query:
        await update.callback_query.answer()
        if edit and update.callback_query.message:
            await update.callback_query.message.edit_text(text=text, parse_mode="HTML", reply_markup=keyboard)
        elif update.callback_query.message:
            await update.callback_query.message.reply_text(text=text, parse_mode="HTML", reply_markup=keyboard)
    elif update.message:
        await update.message.reply_text(text=text, parse_mode="HTML", reply_markup=keyboard)


async def render_home_command(update: Update, context) -> None:
    await render_home(update, context, edit=False)


def callback_router(update: Update, context) -> None:
    raise RuntimeError("callback_router is installed by app.py")


def install(main_module) -> None:
    main_module.callback_router = callback_router
