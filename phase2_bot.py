"""Runtime patch for Phase 2 checkout buttons, preserving the Phase 1 UI code."""
from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import main
import whop_api_phase2

logger = logging.getLogger("neural_gold.phase2_bot")


async def _callback_router(update, context):
    query = update.callback_query
    data = (query.data or "") if query else ""
    if data.startswith("buy:"):
        try:
            await query.answer("Preparing secure checkout…", show_alert=False)
        except Exception:
            pass
        try:
            days = int(data.split(":", 1)[1])
        except (ValueError, IndexError):
            await query.message.reply_text("Checkout option is unavailable.", reply_markup=main.access_keyboard(update))
            return
        user = update.effective_user
        if user is None:
            return
        purchase_url, order_id, error = await whop_api_phase2.create_checkout_for_user(user.id, days)
        if purchase_url:
            await query.message.reply_text(
                f"<b>SECURE CHECKOUT • {days} DAYS</b>\n\nYour personal checkout session is ready.\nUse the button below to complete payment.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 OPEN WHOP CHECKOUT", url=purchase_url)]]),
            )
        else:
            logger.error("Checkout creation failed telegram=%s order=%s error=%s", user.id, order_id, error)
            await query.message.reply_text(
                "<b>CHECKOUT TEMPORARILY UNAVAILABLE</b>\n\nThe payment session could not be created yet.\nPlease try again shortly.",
                parse_mode="HTML",
                reply_markup=main.access_keyboard(update),
            )
        return
    await _original_router(update, context)


_original_router = main.callback_router


def access_keyboard(update):
    lang = main._lang(update)
    rows = [
        [InlineKeyboardButton("🟢 7 DAYS", callback_data="buy:7")],
        [InlineKeyboardButton("🟡 14 DAYS", callback_data="buy:14")],
        [InlineKeyboardButton("🔵 30 DAYS", callback_data="buy:30")],
        [InlineKeyboardButton("💳 I HAVE PAID", callback_data="paid:menu")],
        [InlineKeyboardButton(main.t(lang, "activate"), callback_data="action:token")],
        [InlineKeyboardButton(main.t(lang, "account_status"), callback_data="screen:account")],
        [InlineKeyboardButton(main.t(lang, "support"), callback_data="screen:support")],
        [InlineKeyboardButton(main.t(lang, "back"), callback_data="nav:home"), InlineKeyboardButton(main.t(lang, "menu"), callback_data="nav:home")],
    ]
    return InlineKeyboardMarkup(rows)


def install() -> None:
    main.access_keyboard = access_keyboard
    main.callback_router = _callback_router
