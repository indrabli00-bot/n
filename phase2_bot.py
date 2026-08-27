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


def checkout_link(telegram_id: int, days: int) -> str:
    """Create a short-lived signed URL that Telegram can open directly.

    The URL itself contains no Whop secret and cannot be changed to another
    user/plan without invalidating the signature. The server creates the
    personalized Whop checkout only after the user opens this link.
    """
    expires = int(time.time()) + 15 * 60
    payload = f"{telegram_id}:{days}:{expires}"
    key = (TELEGRAM_BOT_TOKEN or "neural-gold").encode("utf-8")
    signature = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{BELMO_PUBLIC_URL}/checkout/{days}?token={quote(payload + '.' + signature)}"


def access_keyboard(update):
    lang = main._lang(update)
    telegram_id = update.effective_user.id
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟢 7 DAYS", url=checkout_link(telegram_id, 7)),
            InlineKeyboardButton("🟡 14 DAYS", url=checkout_link(telegram_id, 14)),
            InlineKeyboardButton("🔵 30 DAYS", url=checkout_link(telegram_id, 30)),
        ],
        [
            InlineKeyboardButton(main.t(lang, "activate"), callback_data="action:token"),
            InlineKeyboardButton("💳 I HAVE PAID", callback_data="paid:menu"),
        ],
        [InlineKeyboardButton(main.t(lang, "account_status"), callback_data="screen:account")],
        [
            InlineKeyboardButton(main.t(lang, "back"), callback_data="nav:home"),
            InlineKeyboardButton(main.t(lang, "menu"), callback_data="nav:home"),
        ],
    ])


def public_menu_keyboard(update):
    lang = main._lang(update)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 LANGUAGE", callback_data="settings:language")],
        [InlineKeyboardButton("◆ ACCESS / PLANS", callback_data="screen:access")],
        [InlineKeyboardButton(main.t(lang, "back"), callback_data="nav:access")],
    ])


def support_keyboard(update):
    lang = main._lang(update)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(main.t(lang, "contact"), callback_data="support:open")],
        [InlineKeyboardButton(main.t(lang, "back"), callback_data="nav:home"), InlineKeyboardButton(main.t(lang, "menu"), callback_data="nav:home")],
    ])


async def _render_public_menu(update, context):
    lang = main._lang(update)
    text = (
        f"<b>NEURAL GOLD</b>\n{main.DIVIDER}\n\n"
        f"<b>PUBLIC MENU</b>\n\n"
        f"🌐 {main.t(lang, 'language')}\n"
        "Choose your interface language before activation.\n\n"
        "◆ ACCESS / PLANS\n"
        "Select a subscription package to continue."
    )
    await main._present(update, text, public_menu_keyboard(update))


async def _callback_router(update, context):
    query = update.callback_query
    data = (query.data or "") if query else ""
    user = update.effective_user
    if query is None or user is None:
        return

    # Legacy callback links are retained for compatibility with already-sent
    # messages. New menus use URL buttons above, which produce Telegram's
    # native "Open Link" confirmation in a single tap.
    if data.startswith("buy:"):
        await query.answer("Payment link is available from the plan button.", show_alert=True)
        return

    if data == "support:open":
        await query.answer()
        context.user_data["awaiting_support"] = True
        await query.message.reply_text(
            "<b>◉ CONTACT SUPPORT</b>\n\n"
            "Send your question or describe the issue in your next message.\n"
            "Your message will be routed securely to support.",
            parse_mode="HTML",
        )
        return

    if data == "settings:language":
        await query.answer()
        lang = main._lang(update)
        await main._present(update, f"<b>🌐 {main.t(lang, 'choose_language')}</b>\n{main.DIVIDER}\n\n{main.t(lang, 'language_names')}", main.language_keyboard(update))
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
        await main._present(update, "<b>◉ PREMIUM SUPPORT</b>\n" + main.DIVIDER + "\n\nNeed help with access, token activation or account issues?", support_keyboard(update))
        return

    await _original_router(update, context)


async def _unknown_text_handler(update, context):
    if context.user_data.get("awaiting_support"):
        context.user_data["awaiting_support"] = False
        user = update.effective_user
        text = (update.message.text or "").strip()
        if not text:
            await update.message.reply_text("Please describe your issue in a message.")
            context.user_data["awaiting_support"] = True
            return
        support_text = (
            "<b>NEURAL GOLD SUPPORT REQUEST</b>\n\n"
            f"Customer: <b>{main._esc(user.first_name or 'Trader')}</b>\n"
            f"Username: <code>@{main._esc(user.username or 'N/A')}</code>\n"
            f"Telegram ID: <code>{user.id}</code>\n\n"
            f"Message:\n{main._esc(text)}"
        )
        if main.ADMIN_TELEGRAM_ID:
            try:
                await context.bot.send_message(chat_id=main.ADMIN_TELEGRAM_ID, text=support_text, parse_mode="HTML")
            except Exception:
                logger.exception("Failed to route support request")
        await update.message.reply_text(
            "<b>SUPPORT REQUEST SENT</b>\n\nYour message has been routed to support. You will receive a response through Telegram.",
            parse_mode="HTML",
            reply_markup=access_keyboard(update),
        )
        return
    await _original_unknown_text(update, context)


_original_router = main.callback_router
_original_unknown_text = main.unknown_text_handler


def install() -> None:
    main.access_keyboard = access_keyboard
    main.support_keyboard = support_keyboard
    main.callback_router = _callback_router
    main.unknown_text_handler = _unknown_text_handler
