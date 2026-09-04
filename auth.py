'''  
auth.py — Premium access verification middleware.

Access requires both an active local subscription and current membership in
NEURAL GOLD [SIGNALS], unless the caller is the configured administrator.
'''

import functools
import logging
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

import database
from access_gate import is_premium_member
from config import ADMIN_TELEGRAM_ID

logger = logging.getLogger(__name__)


# ── Access check ────────────────────────────────────────────────────────

def verify_token(telegram_id: int) -> tuple[bool, str]:
    """Verify local subscription and live Telegram premium-channel access."""
    # The configured administrator keeps operational access to the bot.
    if telegram_id != ADMIN_TELEGRAM_ID and not is_premium_member(telegram_id):
        return False, "premium_channel_membership_required"

    try:
        user = database.get_user_by_telegram_id(telegram_id)
    except Exception as exc:
        logger.exception("Database error during token verification: %s", exc)
        return False, "Internal error. Please try again later."

    if user is None:
        return False, "not_registered"

    if not user.is_active:
        return False, "inactive"

    if user.subscription_expiry is None:
        return False, "no_expiry"

    expiry_utc = database.normalize_datetime_utc(user.subscription_expiry)
    if expiry_utc is not None and datetime.now(timezone.utc) > expiry_utc:
        try:
            database.update_user(telegram_id, is_active=False)
        except Exception:
            logger.exception("Failed to auto-deactivate expired user %d.", telegram_id)
        return False, "expired"

    return True, "valid"


def is_admin(telegram_id: int) -> bool:
    """Check whether the caller is the configured admin."""
    return telegram_id == ADMIN_TELEGRAM_ID


EXPIRED_MESSAGE = (
    "🔒 <b>Premium access required</b>\n\n"
    "Join <b>NEURAL GOLD [SIGNALS]</b> with an active Neural Gold membership, "
    "then press /start again."
)


def require_auth(func):
    """Decorator for handlers that require active premium access."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user is None:
            return

        is_valid, reason = verify_token(user.id)

        if not is_valid:
            logger.info(
                "Auth denied for user %d (%s): %s",
                user.id,
                user.username or "unknown",
                reason,
            )
            if update.message:
                await update.message.reply_text(EXPIRED_MESSAGE, parse_mode="HTML")
            elif update.callback_query and update.callback_query.message:
                await update.callback_query.message.reply_text(EXPIRED_MESSAGE, parse_mode="HTML")
            return

        context.user_data["auth_reason"] = reason
        return await func(update, context)

    return wrapper


def require_admin(func):
    """Decorator that restricts a handler to ADMIN_TELEGRAM_ID only."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user is None or not is_admin(user.id):
            if update.message:
                await update.message.reply_text(
                    "⛔ <b>Access Denied</b>\n\nThis command is restricted to administrators.",
                    parse_mode="HTML",
                )
            return
        return await func(update, context)

    return wrapper
