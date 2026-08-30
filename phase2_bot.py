"""NEURAL GOLD Phase 2 runtime UI and checkout patch."""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
from urllib.parse import quote

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import auth
import main
from config import BELMO_PUBLIC_URL, TELEGRAM_BOT_TOKEN

logger = logging.getLogger("neural_gold.phase2_bot")

def _t(lang: str, key: str, **kwargs) -> str:
    """Single string source: i18n.py (audit Paket 3 merged phase2.L into i18n)."""
    return main.t(lang, key, **kwargs)


def checkout_link(telegram_id: int, days: int) -> str:
    expires = int(time.time()) + 15 * 60
    payload = f"{telegram_id}:{days}:{expires}"
    key = (TELEGRAM_BOT_TOKEN or "neural-gold").encode("utf-8")
    signature = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{BELMO_PUBLIC_URL}/checkout/{days}?token={quote(payload + '.' + signature)}"


def public_menu_keyboard(update):
    lang = main._lang(update)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🌐 {_t(lang, 'language')}", callback_data="settings:language")],
        [InlineKeyboardButton(f"◆ {_t(lang, 'access')}", callback_data="screen:access")],
        [InlineKeyboardButton(_t(lang, "back"), callback_data="nav:access")],
    ])


async def _render_public_menu(update, context):
    lang = main._lang(update)
    text = (f"<b>[ CONSOLE ]: {_t(lang, 'public_menu')}</b>\n{main.DIVIDER}\n\n"
            "<pre>  MODULE 01 — LANGUAGE ........ OPEN\n"
            "  MODULE 02 — ACCESS &amp; PLANS . OPEN</pre>\n\n"
            f"{_t(lang, 'language')}: {_t(lang, 'choose_language')}\n\n"
            f"{_t(lang, 'access')}: {_t(lang, 'select_plan')}")
    await main._present(update, text, public_menu_keyboard(update))


async def _callback_router(update, context):
    query = update.callback_query
    data = (query.data or "") if query else ""
    user = update.effective_user
    if query is None or user is None:
        return
    lang = main._lang(update)
    if data == "action:token":
        await query.answer()
        context.user_data["awaiting_token"] = True
        await main._present(
            update,
            "<b>[ KEYGEN ]: ACTIVATE TOKEN</b>\n\n"
            f">> {_t(lang, 'enter_activation')}\n"
            f"<i>{_t(lang, 'token_note')}</i>",
            main.access_keyboard(update),
        )
        return
    if data.startswith("buy:"):
        await query.answer(f"[ ERROR ]: INVALID ROUTE — {_t(lang, 'use_package_buttons')}", show_alert=True)
        return
    if data == "support:open":
        await query.answer()
        context.user_data["awaiting_support"] = True
        await query.message.reply_text(f"<b>[ UPLINK ]: {_t(lang, 'support_title')}</b>\n\n{_t(lang, 'support_prompt')}\n{_t(lang, 'support_routed')}", parse_mode="HTML")
        return
    if data == "settings:language":
        await query.answer()
        await main._present(update, f"<b>🌐 {_t(lang, 'choose_language')}</b>\n{main.DIVIDER}\n\n{_t(lang, 'language_names')}", main.language_keyboard(update))
        return
    if data == "nav:home" and not auth.verify_token(user.id)[0]:
        await query.answer()
        await _render_public_menu(update, context)
        return
    if data == "nav:access":
        await query.answer()
        await main.render_access(update, context)
        return
    if data == "screen:support":
        await query.answer()
        await main._present(update, f"<b>[ UPLINK ]: {_t(lang, 'support_title')}</b>\n{main.DIVIDER}\n\n{_t(lang, 'support_prompt')}", main.support_keyboard(update))
        return
    await _original_router(update, context)


async def _unknown_text_handler(update, context):
    if context.user_data.get("awaiting_support"):
        context.user_data["awaiting_support"] = False
        user = update.effective_user
        text = (update.message.text or "").strip()
        lang = main._lang(update)
        if not text:
            await update.message.reply_text(_t(lang, 'support_empty'))
            context.user_data["awaiting_support"] = True
            return
        support_text = (f"<b>[ INCOMING ]: NEURAL GOLD SUPPORT REQUEST</b>\n\n"
                        f"CUSTOMER: <b>{main._esc(user.first_name or 'Trader')}</b>\n"
                        f"USERNAME: <code>@{main._esc(user.username or 'N/A')}</code>\n"
                        f"TELEGRAM_ID: <code>{user.id}</code>\n\nMESSAGE_LOG:\n{main._esc(text)}")
        if main.ADMIN_TELEGRAM_ID:
            try:
                await context.bot.send_message(chat_id=main.ADMIN_TELEGRAM_ID, text=support_text, parse_mode="HTML")
            except Exception:
                logger.exception("Failed to route support request")
        sent_body = _t(lang, 'support_sent').split("\n\n", 1)[-1]
        await update.message.reply_text(
            f"<b>[ LOG ]: SUPPORT REQUEST TRANSMITTED</b>\n\n{sent_body}",
            parse_mode="HTML",
            reply_markup=main.access_keyboard(update),
        )
        return
    await _original_unknown_text(update, context)


_original_router = main.callback_router
_original_unknown_text = main.unknown_text_handler

