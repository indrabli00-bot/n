"""Low-latency /start path for the Belmo Telegram webhook runtime."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

import auth
import database
import main
import terminal_style
from i18n import detect_language, t

logger = logging.getLogger("neural_gold.instant_start")


def _instant_keyboard(lang: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("🔒 MARKET PULSE", callback_data="screen:price"),
            InlineKeyboardButton("🔒 NEURAL STRIKES", callback_data="screen:signal"),
        ],
        [InlineKeyboardButton("🔒 STRUCTURE MAP", callback_data="screen:analysis")],
        [InlineKeyboardButton(f"💎 {t(lang, 'activate_premium')}", callback_data="screen:activate")],
        [
            InlineKeyboardButton(f"🏠 {t(lang, 'menu').removeprefix('⌂ ').strip().title()}", callback_data="nav:home"),
            InlineKeyboardButton(f"👨‍💼 {t(lang, 'account').strip().title()}", callback_data="screen:account"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def _instant_text(user, lang: str) -> str:
    now = datetime.now(timezone.utc).strftime("[ %Y-%m-%d %H:%M:%S UTC ]")
    operator = terminal_style.word_wrap(user.first_name or "OPERATOR", 70)[0]
    terminal = terminal_style.render_terminal_box(
        "\n".join(
            [
                "[ SYSTEM ]: INITIALIZING...",
                "[ STATUS ]: CONNECTING OPERATOR...",
                "[ ACCESS ]: CHECKING CLEARANCE...",
            ]
        )
    )
    return f"NEURAL GOLD {main.NEURAL_VERSION}\n{now}\nOPERATOR : {operator}\nSTATUS   : Connecting 🟡\n\n<pre>{terminal}</pre>\n\n>> {t(lang, 'select_module')}"


async def _initialize_and_refresh(message, update: Update, user, lang: str) -> None:
    """Finish registration off the request path and replace the shell in-place."""
    try:
        existing = await asyncio.to_thread(database.get_user_by_telegram_id, user.id)
        if existing is None:
            await asyncio.to_thread(
                database.create_user,
                user.id,
                user.username,
                user.first_name,
                lang,
            )
            logger.info("New user registered: %d (%s)", user.id, user.username)

        active = await asyncio.to_thread(lambda: auth.verify_token(user.id)[0])
        terminal = "\n".join(
            [
                "[ SYSTEM ]: INITIALIZING...",
                "[ STATUS ]: SYNCING GLOBAL BULLION RESERVES...",
                "[ ACCESS ]: GRANTED // WELCOME OPERATOR" if active else "[ ACCESS ]: PENDING // CLEARANCE REQUIRED",
            ]
        )
        text = f"NEURAL GOLD {main.NEURAL_VERSION}\n{datetime.now(timezone.utc).strftime('[ %Y-%m-%d %H:%M:%S UTC ]')}\nOPERATOR : {main._safe_user_name(user)}\nSTATUS   : {'Aktif 🟢' if active else 'Nonaktif 🔴'}\n\n<pre>{terminal_style.render_terminal_box(terminal)}</pre>\n\n>> {t(lang, 'select_module')}"
        keyboard = await asyncio.to_thread(main.home_keyboard, update)
        await message.edit_text(text=text, parse_mode="HTML", reply_markup=keyboard)
    except Exception:
        logger.exception("Background /start initialization failed; instant shell retained")


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Respond immediately, then perform database/auth work in the background."""
    user = update.effective_user
    message = update.message
    if user is None or message is None:
        raise ApplicationHandlerStop

    lang = detect_language(user.language_code)
    shell = await message.reply_text(
        _instant_text(user, lang),
        parse_mode="HTML",
        reply_markup=_instant_keyboard(lang),
    )
    context.application.create_task(
        _initialize_and_refresh(shell, update, user, lang),
        update=update,
        name="instant_start_finalize",
    )
    raise ApplicationHandlerStop
