"""Safety boundary for Telegram callback handlers in the Belmo runtime.

The customer-facing callback path must never leak an unexpected exception into
PTB's global error handler. A failed callback is converted into a recoverable
UI state while the original exception remains fully logged for diagnosis.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update

import terminal_style
from i18n import detect_language, t

logger = logging.getLogger("neural_gold.callback_guard")


def _safe_keyboard(update: Update) -> InlineKeyboardMarkup:
    user = update.effective_user
    lang = detect_language(user.language_code if user else None)
    nav = terminal_style.render_persistent_nav(lang).inline_keyboard[0]
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t(lang, "menu"), callback_data="screen:menu")],
            list(nav),
        ]
    )


def _safe_message(update: Update) -> str:
    user = update.effective_user
    lang = detect_language(user.language_code if user else None)
    return (
        f"<b>[ SYSTEM ]: {t(lang, 'module_unavailable')}</b>\n\n"
        f">> {t(lang, 'tap_menu_retry')}"
    )


def install(main_module) -> None:
    """Wrap the canonical callback router once, without changing its routes."""
    current = getattr(main_module, "callback_router")
    if getattr(current, "_neural_gold_guarded", False):
        return

    async def guarded(update: Update, context) -> None:
        try:
            await current(update, context)
        except Exception:
            logger.exception(
                "Unhandled Telegram callback failure user=%s data=%s",
                getattr(update.effective_user, "id", None),
                getattr(update.callback_query, "data", None),
            )
            query = update.callback_query
            if query is None:
                return
            try:
                await query.answer(show_alert=False)
            except Exception:
                pass
            try:
                await query.edit_message_text(
                    text=_safe_message(update),
                    parse_mode="HTML",
                    reply_markup=_safe_keyboard(update),
                )
                return
            except Exception:
                logger.exception("Could not replace failed callback message")
            try:
                if query.message:
                    await query.message.reply_text(
                        text=_safe_message(update),
                        parse_mode="HTML",
                        reply_markup=_safe_keyboard(update),
                    )
            except Exception:
                logger.exception("Could not send callback recovery message")

    guarded._neural_gold_guarded = True
    main_module.callback_router = guarded
