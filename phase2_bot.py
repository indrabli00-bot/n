"""NEURAL GOLD Phase 2 runtime UI and checkout patch."""
from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import auth
import main
import whop_api_phase2

logger = logging.getLogger("neural_gold.phase2_bot")


def access_keyboard(update):
    lang = main._lang(update)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 7 DAYS", callback_data="buy:7")],
        [InlineKeyboardButton("🟡 14 DAYS", callback_data="buy:14")],
        [InlineKeyboardButton("🔵 30 DAYS", callback_data="buy:30")],
        [InlineKeyboardButton("💳 I HAVE PAID", callback_data="paid:menu")],
        [InlineKeyboardButton(main.t(lang, "activate"), callback_data="action:token")],
        [InlineKeyboardButton(main.t(lang, "account_status"), callback_data="screen:account")],
        [InlineKeyboardButton(main.t(lang, "back"), callback_data="nav:home"), InlineKeyboardButton(main.t(lang, "menu"), callback_data="nav:home")],
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

    if data.startswith("buy:"):
        try:
            days = int(data.split(":", 1)[1])
        except (ValueError, IndexError):
            await query.answer("Payment option unavailable.", show_alert=True)
            return
        purchase_url, order_id, error = await whop_api_phase2.create_checkout_for_user(user.id, days)
        if purchase_url:
            try:
                # Open the personalized Whop payment directly from the callback.
                # The order metadata remains available for automatic fulfillment.
                await query.answer(url=purchase_url)
            except Exception:
                await query.message.reply_text(
                    "<b>PAYMENT LINK READY</b>\n\nTap below to open payment.",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 OPEN PAYMENT", url=purchase_url)]]),
                )
        else:
            logger.error("Checkout creation failed telegram=%s order=%s error=%s", user.id, order_id, error)
            await query.answer("Payment link is temporarily unavailable. Please try again shortly.", show_alert=True)
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
