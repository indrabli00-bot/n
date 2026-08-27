"""Whop Standard Webhooks verification and Phase 2 fulfillment."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import datetime, timezone
from typing import Any

import database
import whop_storage
from config import WHOP_WEBHOOK_SECRET

logger = logging.getLogger("neural_whop_webhook")
PLAN_DURATIONS = {"plan_ksl11weFJ0z41": 7, "plan_Yc1JnCIP8jgII": 14, "plan_JDgh0geRuoSFX": 30}


def verify_signature(payload: bytes, headers: dict) -> dict:
    if not WHOP_WEBHOOK_SECRET:
        raise ValueError("WHOP_WEBHOOK_SECRET is not configured")
    h = {str(k).lower(): str(v) for k, v in headers.items()}
    webhook_id, timestamp, signature = h.get("webhook-id", ""), h.get("webhook-timestamp", ""), h.get("webhook-signature", "")
    if not webhook_id or not timestamp or not signature:
        raise ValueError("Missing webhook verification headers")
    try:
        ts = int(timestamp)
    except ValueError as exc:
        raise ValueError("Invalid webhook timestamp") from exc
    if abs(time.time() - ts) > 300:
        raise ValueError("Webhook timestamp outside 5 minute tolerance")
    signed = f"{webhook_id}.{timestamp}.".encode() + payload
    digest = base64.b64encode(hmac.new(WHOP_WEBHOOK_SECRET.encode(), signed, hashlib.sha256).digest()).decode()
    expected = f"v1,{digest}"
    if not any(hmac.compare_digest(item.strip(), expected) for item in signature.split(" ")):
        raise ValueError("Invalid webhook signature")
    return json.loads(payload.decode())


def _token() -> str:
    return f"XAU-NEURAL-{secrets.token_hex(8).upper()}"


def handle_payment_succeeded(payment: dict) -> tuple[str, int, str] | None:
    metadata = payment.get("metadata") or {}
    order_id = str(metadata.get("neural_order_id") or "")
    payment_id = str(payment.get("id") or "")
    plan = payment.get("plan") or {}
    plan_id = str(plan.get("id") or payment.get("plan_id") or "")
    if not order_id or not payment_id:
        logger.error("Payment missing order/payment identity payment=%s", payment_id)
        return None
    order = whop_storage.get_order(order_id)
    if order is None:
        logger.error("Unknown Neural Gold order_id=%s payment=%s", order_id, payment_id)
        return None
    duration = PLAN_DURATIONS.get(plan_id) or PLAN_DURATIONS.get(order["plan_id"])
    if duration is None or duration != order["duration_days"]:
        whop_storage.update_order(order_id, status="rejected_plan_mismatch", payment_id=payment_id)
        return None
    existing = whop_storage.get_order_by_payment(payment_id)
    if existing is not None and existing.get("token_hash"):
        return None
    raw_token = _token()
    if not database.add_token_to_pool(raw_token, duration_days=duration):
        whop_storage.update_order(order_id, status="fulfillment_failed", payment_id=payment_id)
        return None
    token_hash = hashlib.sha256(raw_token.strip().encode()).hexdigest()
    membership = payment.get("membership") or {}
    whop_storage.update_order(order_id, payment_id=payment_id, membership_id=str(membership.get("id") or "") or None,
                              token_hash=token_hash, paid_at=datetime.now(timezone.utc), status="token_issued")
    logger.info("Whop payment fulfilled payment=%s order=%s telegram=%s duration=%sd", payment_id, order_id, order["telegram_id"], duration)
    return raw_token, duration, order_id


def handle_event(event_type: str, data: dict) -> tuple[str, int, str] | None:
    if event_type == "payment.succeeded":
        return handle_payment_succeeded(data)
    metadata = data.get("metadata") or {}
    order_id = str(metadata.get("neural_order_id") or "")
    if not order_id:
        return None
    payment_id = str(data.get("id") or "") or None
    if event_type == "payment.failed":
        whop_storage.update_order(order_id, status="payment_failed", payment_id=payment_id)
    elif event_type in {"refund.created", "refund.updated"}:
        whop_storage.update_order(order_id, status="refunded")
    elif event_type == "membership.deactivated":
        whop_storage.update_order(order_id, status="membership_deactivated")
    elif event_type == "membership.cancel_at_period_end_changed":
        whop_storage.update_order(order_id, status="cancel_at_period_end_changed")
    elif event_type == "membership.activated":
        whop_storage.update_order(order_id, status="membership_active")
    return None


async def notify_customer(bot: Any, telegram_id: int, raw_token: str, duration_days: int, order_id: str) -> None:
    try:
        await bot.send_message(chat_id=telegram_id, text=(
            "<b>✓ PAYMENT VERIFIED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Your <b>{duration_days}-day</b> Neural Gold access is ready.\n\n"
            "<b>SECURE ACTIVATION TOKEN</b>\n"
            f"<code>{raw_token}</code>\n\n"
            "Open <b>ACCESS / PLANS</b> → <b>ACTIVATE</b> and enter this token.\n\n"
            "This token is single-use."
        ), parse_mode="HTML")
        whop_storage.update_order(order_id, notified_at=datetime.now(timezone.utc), status="customer_notified")
    except Exception as exc:
        logger.exception("Failed to notify Telegram user %s for order %s: %s", telegram_id, order_id, exc)
        whop_storage.update_order(order_id, status="token_issued_notification_failed")
