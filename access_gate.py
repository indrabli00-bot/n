"""Telegram premium-channel access gate for NEURAL GOLD.

Access is granted only while Telegram reports the user as a member of the
Whop-managed premium channel. The channel ID is configured by
TELEGRAM_PREMIUM_CHAT_ID.
"""
from __future__ import annotations

import logging
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

logger = logging.getLogger("neural_gold.access_gate")

MEMBER_STATUSES = {"creator", "administrator", "member"}
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
PREMIUM_CHAT_ID = os.getenv("TELEGRAM_PREMIUM_CHAT_ID", "").strip()
TIMEOUT_SECONDS = float(os.getenv("TELEGRAM_ACCESS_GATE_TIMEOUT", "8"))


def _telegram_api(method: str, payload: dict) -> dict:
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    body = urlencode(payload).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(data.get("description", f"Telegram API error: {method}"))
    return data["result"]


def is_premium_member(user_id: int) -> bool:
    """Return True only for a current member/admin/owner of the premium channel."""
    if not PREMIUM_CHAT_ID:
        logger.error("TELEGRAM_PREMIUM_CHAT_ID is not configured")
        return False
    try:
        member = _telegram_api(
            "getChatMember",
            {"chat_id": PREMIUM_CHAT_ID, "user_id": user_id},
        )
        status = member.get("status")
        if status in MEMBER_STATUSES:
            return True
        if status == "restricted":
            return bool(member.get("is_member"))
        return False
    except Exception:
        logger.exception("Premium channel check failed for user %s", user_id)
        return False


def access_denied_reason(user_id: int) -> str:
    if not PREMIUM_CHAT_ID:
        return "premium_channel_not_configured"
    return "premium_channel_membership_required" if not is_premium_member(user_id) else ""
