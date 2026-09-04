"""Live Telegram membership gate for the Whop-managed premium channel."""
from __future__ import annotations

import json
import logging
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_PREMIUM_CHAT_ID

logger = logging.getLogger("neural_gold.access_gate")

MEMBER_STATUSES = {"creator", "administrator", "member"}
TIMEOUT_SECONDS = float(os.getenv("TELEGRAM_ACCESS_GATE_TIMEOUT", "8"))


def _telegram_api(method: str, payload: dict) -> dict:
    token = TELEGRAM_BOT_TOKEN.strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    request = Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=urlencode(payload).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(data.get("description", f"Telegram API error: {method}"))
    return data["result"]


def is_premium_member(user_id: int) -> bool:
    """Return True only when Telegram confirms current premium-channel membership."""
    chat_id = TELEGRAM_PREMIUM_CHAT_ID.strip()
    if not chat_id:
        logger.error("TELEGRAM_PREMIUM_CHAT_ID is not configured")
        return False
    try:
        member = _telegram_api("getChatMember", {"chat_id": chat_id, "user_id": user_id})
        status = member.get("status")
        if status in MEMBER_STATUSES:
            return True
        if status == "restricted":
            return bool(member.get("is_member"))
        return False
    except Exception:
        logger.exception("Premium channel membership check failed for user %s", user_id)
        return False


def access_denied_reason(user_id: int) -> str:
    if not TELEGRAM_PREMIUM_CHAT_ID.strip():
        return "premium_channel_not_configured"
    return "premium_channel_membership_required" if not is_premium_member(user_id) else ""
