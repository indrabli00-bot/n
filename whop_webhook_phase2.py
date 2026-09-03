"""Whop Standard Webhooks verification and Phase 2 fulfillment."""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import database
import i18n
import whop_storage
from config import WHOP_WEBHOOK_SECRET
from visuals import visual_path

logger = logging.getLogger("neural_whop_webhook")
PLAN_DURATIONS = {"plan_ksl11weFJ0z41": 7, "plan_Yc1JnCIP8jgII": 14, "plan_JDgh0geRuoSFX": 30}
STALE_FULFILLMENT_MINUTES = 10
MAX_FULFILLMENT_ATTEMPTS = 3


class FulfillmentRetryableError(RuntimeError):
    """Signal that Whop should retry a payment webhook."""


def _signing_key_candidates(secret: str) -> list[bytes]:
    value = secret.strip()
    candidates: list[bytes] = []
    if value.startswith("whsec_"):
        encoded = value[6:]
        try:
            candidates.append(base64.b64decode(encoded + "=" * (-len(encoded) % 4), validate=True))
        except (binascii.Error, ValueError):
            candidates.append(encoded.encode("utf-8"))
        candidates.append(value.encode("utf-8"))
    elif value.startswith("ws_"):
        candidates.extend((value.encode("utf-8"), value[3:].encode("utf-8")))
    else:
        candidates.append(value.encode("utf-8"))
    return candidates


def verify_signature(payload: bytes, headers: dict) -> dict:
    if not WHOP_WEBHOOK_SECRET:
        raise ValueError("WHOP_WEBHOOK_SECRET is not configured")
    h = {str(k).lower(): str(v) for k, v in headers.items()}
    webhook_id = h.get("webhook-id", "")
    timestamp = h.get("webhook-timestamp", "")
    signature = h.get("webhook-signature", "")
    if not webhook_id or not timestamp or not signature:
        raise ValueError("Missing webhook verification headers")
    try:
        ts = int(timestamp)
    except ValueError as exc:
        raise ValueError("Invalid webhook timestamp") from exc
    if abs(time.time() - ts) > 300:
        raise ValueError("Webhook timestamp outside 5 minute tolerance")
    signed = f"{webhook_id}.{timestamp}.".encode() + payload
    for key in _signing_key_candidates(WHOP_WEBHOOK_SECRET):
        digest = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode("ascii")
        if any(item.startswith("v1,") and hmac.compare_digest(item[3:], digest) for item in signature.split()):
            return json.loads(payload.decode("utf-8"))
    raise ValueError("Invalid webhook signature")


def _resolve_duration(plan_id: str, order: dict | None = None) -> int:
    plan_id = str(plan_id or "")
    duration = PLAN_DURATIONS.get(plan_id)
    if duration is None:
        raise FulfillmentRetryableError(f"Unknown or invalid plan duration: {plan_id}")
    if order is not None:
        try:
            order_days = int(order["duration_days"])
        except (KeyError, TypeError, ValueError) as exc:
            raise FulfillmentRetryableError(f"Invalid stored duration for order plan={plan_id}") from exc
        if order_days != duration:
            raise FulfillmentRetryableError(f"Plan duration mismatch: plan={plan_id} expected={duration} order={order_days}")
    return duration


def _validate_payment_plan(payment: dict, order: dict | None = None) -> tuple[str, int]:
    plan = payment.get("plan") or {}
    plan_id = str(plan.get("id") or payment.get("plan_id") or "")
    duration = _resolve_duration(plan_id, order)
    raw_days = (payment.get("metadata") or {}).get("plan_days")
    if raw_days not in (None, ""):
        try:
            metadata_days = int(raw_days)
        except (TypeError, ValueError) as exc:
            raise FulfillmentRetryableError(f"Invalid metadata.plan_days for plan {plan_id}") from exc
        if metadata_days != duration:
            raise FulfillmentRetryableError(f"Plan duration mismatch: plan={plan_id} expected={duration} metadata={metadata_days}")
    return plan_id, duration


def handle_payment_succeeded(payment: dict) -> tuple[str, int, str] | None:
    metadata = payment.get("metadata") or {}
    order_id = str(metadata.get("neural_order_id") or "")
    payment_id = str(payment.get("id") or "")
    if not order_id or not payment_id:
        raise FulfillmentRetryableError(f"Payment missing order/payment identity payment={payment_id}")
    bound_order = whop_storage.get_order_by_payment(payment_id)
    if bound_order is not None and str(bound_order.get("id")) != order_id:
        raise FulfillmentRetryableError(f"Payment {payment_id} already bound to order {bound_order.get('id')}")
    order = whop_storage.get_order(order_id)
    plan_id, duration = _validate_payment_plan(payment, order)
    if order is None:
        try:
            telegram_id = int(str(metadata.get("telegram_id") or ""))
        except (TypeError, ValueError) as exc:
            raise FulfillmentRetryableError("Missing valid metadata.telegram_id") from exc
        if not whop_storage.create_order(order_id, telegram_id, plan_id, duration):
            raise FulfillmentRetryableError(f"Failed to recreate order {order_id}")
        order = whop_storage.get_order(order_id)
        if order is None:
            raise FulfillmentRetryableError(f"Recreated order {order_id} cannot be read")
    claim_id = whop_storage.claim_fulfillment(payment_id, order_id, stale_minutes=STALE_FULFILLMENT_MINUTES)
    if not claim_id:
        return None
    try:
        raw_token, _ = database.fulfill_payment(int(order["telegram_id"]), duration, order_id, payment_id, claim_id)
    except Exception as exc:
        attempts = whop_storage.record_fulfillment_failure(payment_id, str(exc)[:200])
        whop_storage.update_order(order_id, status="fulfillment_failed", payment_id=payment_id)
        logger.exception("Fulfillment failed order=%s payment=%s attempts=%s", order_id, payment_id, attempts)
        raise FulfillmentRetryableError(f"Atomic fulfillment failed order={order_id} payment={payment_id}") from exc
    membership = payment.get("membership") or {}
    whop_storage.update_order(order_id, membership_id=str(membership.get("id") or "") or None)
    return raw_token, duration, order_id


def _event_metadata(event_type: str, data: dict) -> tuple[dict, str | None, str | None]:
    metadata = data.get("metadata") or {}
    payment_id = str(data.get("id") or "") or None
    membership_id = None
    if event_type.startswith("refund."):
        payment = data.get("payment") or {}
        payment_id = str(payment.get("id") or payment_id or "") or None
        metadata = payment.get("metadata") or metadata
        membership_id = str((payment.get("membership") or {}).get("id") or "") or None
    elif event_type.startswith("membership."):
        membership_id = str(data.get("id") or "") or None
    return metadata, payment_id, membership_id


def _is_full_successful_refund(data: dict) -> bool:
    if str(data.get("status") or "").lower() != "succeeded":
        return False
    payment = data.get("payment") or {}
    try:
        return float(data.get("amount")) >= float(payment.get("total"))
    except (TypeError, ValueError):
        return False


def handle_event(event_type: str, data: dict) -> tuple[str, int, str] | None:
    if event_type == "payment.succeeded":
        return handle_payment_succeeded(data)
    metadata, payment_id, membership_id = _event_metadata(event_type, data)
    order_id = str(metadata.get("neural_order_id") or "")
    order = whop_storage.get_order(order_id) if order_id else None
    if order is None and payment_id:
        order = whop_storage.get_order_by_payment(payment_id)
        order_id = str(order["id"]) if order else ""
    if order is None and membership_id:
        order = whop_storage.get_order_by_membership(membership_id)
        order_id = str(order["id"]) if order else ""
    if not order_id:
        return None
    if event_type == "payment.failed":
        whop_storage.update_order(order_id, status="payment_failed", payment_id=payment_id)
    elif event_type in {"refund.created", "refund.updated"}:
        status = str(data.get("status") or "pending").lower()
        whop_storage.update_order(order_id, status=f"refund_{status}", payment_id=payment_id)
        if _is_full_successful_refund(data):
            whop_storage.revoke_order_access(order_id)
    elif event_type == "membership.deactivated":
        whop_storage.update_order(order_id, status="membership_deactivated", membership_id=membership_id)
        whop_storage.revoke_order_access(order_id)
    elif event_type == "membership.cancel_at_period_end_changed":
        whop_storage.update_order(order_id, status="cancel_at_period_end_changed", membership_id=membership_id)
    elif event_type == "membership.activated":
        whop_storage.update_order(order_id, status="membership_active", membership_id=membership_id)
    return None


async def notify_customer(bot: Any, telegram_id: int, duration_days: int, order_id: str) -> None:
    lang = database.get_user_language(telegram_id)
    try:
        asset = visual_path("success")
        if asset:
            try:
                with open(asset, "rb") as fh:
                    await bot.send_photo(chat_id=telegram_id, photo=fh, caption="<b>[ ACCESS ]: PAYMENT CONFIRMED</b>\n<i>NEURAL GOLD v3.2</i>", parse_mode="HTML")
            except Exception:
                logger.exception("Premium payment visual delivery failed")
        await bot.send_message(
            chat_id=telegram_id,
            text=("<b>[ SYSTEM ]: PAYMENT VERIFIED // FULFILLMENT COMPLETE</b>\n"
                  "━━━━━━━━━━━━━━━━━━━━\n\n"
                  f"[ ACCESS ]: <b>{i18n.t(lang, 'access_now_active', days=duration_days)}</b>\n\n"
                  f"{i18n.t(lang, 'auto_activated_note')}\n\n"
                  ">> [ CORE ]: ALL INTELLIGENCE MODULES UNLOCKED. PRESS /start."),
            parse_mode="HTML",
        )
        whop_storage.update_order(order_id, notified_at=datetime.now(timezone.utc), status="customer_notified")
    except Exception:
        logger.exception("Failed to notify Telegram user %s for order %s", telegram_id, order_id)
        whop_storage.update_order(order_id, status="active_notification_failed")


def recover_stale_fulfillments(stale_minutes: int = STALE_FULFILLMENT_MINUTES, max_attempts: int = MAX_FULFILLMENT_ATTEMPTS) -> dict:
    report = {"recovered": [], "skipped": [], "exhausted": []}
    for row in whop_storage.list_stale_claims(stale_minutes=stale_minutes, max_attempts=max_attempts):
        payment_id, order_id = row["payment_id"], row["order_id"]
        claim_id = whop_storage.claim_fulfillment(payment_id, order_id, stale_minutes=stale_minutes)
        if not claim_id:
            report["skipped"].append(payment_id)
            continue
        try:
            order = whop_storage.get_order(order_id) or {}
            database.fulfill_payment(int(order["telegram_id"]), int(order["duration_days"]), order_id, payment_id, claim_id)
            report["recovered"].append({"payment_id": payment_id, "order_id": order_id, "telegram_id": order.get("telegram_id"), "duration_days": order.get("duration_days")})
        except Exception as exc:
            attempts = whop_storage.record_fulfillment_failure(payment_id, str(exc)[:200])
            item = {"payment_id": payment_id, "order_id": order_id, "attempts": attempts, "error": str(exc)[:160]}
            (report["exhausted"] if attempts >= max_attempts else report["skipped"]).append(item if attempts >= max_attempts else payment_id)
    return report


def reconcile_payment(payment_id: str) -> dict:
    fulfillment = whop_storage.get_fulfillment(payment_id)
    order = whop_storage.get_order_by_payment(payment_id)
    if order is None and fulfillment:
        order = whop_storage.get_order(fulfillment["order_id"])
    if order is None:
        return {"ok": False, "reason": "ORDER/PAYMENT NOT FOUND"}
    if fulfillment and fulfillment.get("status") == "fulfilled":
        user = database.get_user_by_telegram_id(int(order["telegram_id"]))
        return {"ok": True, "status": "ALREADY FULFILLED", "telegram_id": order["telegram_id"], "expiry": user.subscription_expiry.isoformat() if user and user.subscription_expiry else None}
    if fulfillment is None:
        return {"ok": False, "reason": "NO FULFILLMENT CLAIM — REMOTE WHOP REVALIDATION REQUIRED"}
    claim_id = whop_storage.claim_fulfillment(payment_id, order["id"], stale_minutes=0)
    if not claim_id:
        return {"ok": False, "reason": "CLAIM FAILED — processing by another worker"}
    try:
        database.fulfill_payment(int(order["telegram_id"]), int(order["duration_days"]), order["id"], payment_id, claim_id)
        user = database.get_user_by_telegram_id(int(order["telegram_id"]))
        return {"ok": True, "status": "FULFILLED", "telegram_id": order["telegram_id"], "expiry": user.subscription_expiry.isoformat() if user and user.subscription_expiry else None}
    except Exception as exc:
        whop_storage.record_fulfillment_failure(payment_id, str(exc)[:200])
        return {"ok": False, "reason": str(exc)[:160]}


import whop_api_phase2  # noqa: E402


async def reconcile_payment_remote(payment_id: str) -> dict:
    payment = await whop_api_phase2.fetch_payment(payment_id)
    status = str(payment.get("status") or "").lower()
    substatus = str(payment.get("substatus") or "").lower()
    if status != "paid" and substatus != "succeeded":
        return {"ok": False, "reason": f"WHOP_STATUS_{status.upper() or substatus.upper() or 'UNKNOWN'}"}
    metadata = payment.get("metadata") or {}
    bound_order = whop_storage.get_order_by_payment(payment_id)
    supplied_order_id = str(metadata.get("neural_order_id") or "")
    order_id = str(bound_order["id"]) if bound_order is not None else (supplied_order_id or f"ng_rec_{payment_id[-12:].lower()}")
    try:
        telegram_id = int(str(metadata.get("telegram_id") or ""))
    except (TypeError, ValueError):
        telegram_id = int(bound_order["telegram_id"]) if bound_order is not None else 0
    if telegram_id <= 0:
        return {"ok": False, "reason": "METADATA_TELEGRAM_ID_MISSING"}
    try:
        plan_id, duration = _validate_payment_plan(payment, bound_order)
    except FulfillmentRetryableError as exc:
        return {"ok": False, "reason": str(exc)}
    existing_order = bound_order or whop_storage.get_order(order_id)
    if existing_order is not None:
        try:
            _resolve_duration(plan_id, existing_order)
        except FulfillmentRetryableError as exc:
            return {"ok": False, "reason": str(exc)}
        if int(existing_order["telegram_id"]) != telegram_id:
            return {"ok": False, "reason": "ORDER_TELEGRAM_ID_MISMATCH"}
    else:
        if not whop_storage.create_order(order_id, telegram_id, plan_id, duration):
            return {"ok": False, "reason": "FAILED_TO_CREATE_LOCAL_ORDER"}
    membership_id = str((payment.get("membership") or {}).get("id") or "") or None
    whop_storage.update_order(order_id, payment_id=payment_id, membership_id=membership_id)
    claim_id = whop_storage.claim_fulfillment(payment_id, order_id, stale_minutes=0)
    if not claim_id:
        return {"ok": True, "status": "ALREADY FULFILLED", "telegram_id": telegram_id}
    try:
        database.fulfill_payment(telegram_id, duration, order_id, payment_id, claim_id)
    except Exception as exc:
        whop_storage.record_fulfillment_failure(payment_id, str(exc)[:200])
        raise FulfillmentRetryableError(f"Remote fulfillment failed payment={payment_id}") from exc
    return {"ok": True, "status": "FULFILLED VIA WHOP REVALIDATION", "telegram_id": telegram_id, "duration_days": duration}


async def reconcile_payment_full(payment_id: str) -> dict:
    local = reconcile_payment(payment_id)
    if local.get("ok"):
        return local
    if not str(payment_id or "").strip():
        return local
    remote = await reconcile_payment_remote(payment_id)
    if remote.get("ok"):
        return remote
    return {"ok": False, "reason": f"{local.get('reason', '')} | Whop: {remote.get('reason', '')}"}
