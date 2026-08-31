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
PLAN_DURATIONS = {
    "plan_ksl11weFJ0z41": 7,
    "plan_Yc1JnCIP8jgII": 14,
    "plan_JDgh0geRuoSFX": 30,
}

# Fulfillment lock (audit round-2): reclaim window for stale 'processing' claims.
STALE_FULFILLMENT_MINUTES = 10


class FulfillmentRetryableError(RuntimeError):
    """Signal that Whop should retry a payment webhook."""


def _signing_key_candidates(secret: str) -> list[bytes]:
    """Kandidat kunci HMAC untuk berbagai konvensi prefix (fulfillment ops).

    Standard Webhooks: 'whsec_' = base64-encoded key.
    Whop: 'ws_' = secret string mentah (RAW) — tanpa base64.
    Semua kandidat dicoba agar perbedaan konvensi tidak memblokir fulfillment.
    """
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
        candidates.append(value.encode("utf-8"))       # full string termasuk prefix
        candidates.append(value[3:].encode("utf-8"))   # tanpa prefix
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

    signed = f"{webhook_id}.{timestamp}.".encode("utf-8") + payload
    passed = signature.split()
    matched = False
    for key in _signing_key_candidates(WHOP_WEBHOOK_SECRET):
        digest = base64.b64encode(
            hmac.new(key, signed, hashlib.sha256).digest()
        ).decode("ascii")
        if any(
            item.startswith("v1,") and hmac.compare_digest(item[3:], digest)
            for item in passed
        ):
            matched = True
            break
    if not matched:
        raise ValueError("Invalid webhook signature")
    return json.loads(payload.decode("utf-8"))


def handle_payment_succeeded(payment: dict) -> tuple[str, int, str] | None:
    metadata = payment.get("metadata") or {}
    order_id = str(metadata.get("neural_order_id") or "")
    payment_id = str(payment.get("id") or "")
    plan = payment.get("plan") or {}
    plan_id = str(plan.get("id") or payment.get("plan_id") or "")
    if not order_id or not payment_id:
        raise FulfillmentRetryableError(
            f"Payment missing order/payment identity payment={payment_id}"
        )

    duration = PLAN_DURATIONS.get(plan_id)
    order = whop_storage.get_order(order_id)
    if order is None:
        # State sync (fulfillment ops): DB non-durable / redeploy bisa menghapus
        # order lokal. Buat ulang dari metadata Whop agar retry TETAP memfulfill
        # (tanpa ini, customer sudah bayar tapi order hilang selamanya).
        tid_raw = str(metadata.get("telegram_id") or "")
        try:
            tid = int(tid_raw)
        except ValueError:
            raise FulfillmentRetryableError(
                f"Order {order_id} tidak ada di DB dan metadata.telegram_id tidak valid"
            )
        if duration is None:
            raise FulfillmentRetryableError(f"Plan {plan_id} tidak dikenal untuk order {order_id}")
        if not whop_storage.create_order(order_id, tid, plan_id or "unknown", duration):
            raise FulfillmentRetryableError(f"Gagal membuat ulang order {order_id}")
        order = whop_storage.get_order(order_id)
        if order is None:
            raise FulfillmentRetryableError(f"Order {order_id} gagal dibuat ulang")
    if duration is None:
        duration = int(order["duration_days"])
    if duration != order["duration_days"]:
        whop_storage.update_order(
            order_id, status="rejected_plan_mismatch", payment_id=payment_id
        )
        return None

    existing = whop_storage.get_order_by_payment(payment_id)
    if existing is not None and existing.get("token_hash"):
        return None

    # Fulfillment lock + fencing (fulfillment ops): atomic, payment_id-keyed idempotency.
    claim_id = whop_storage.claim_fulfillment(payment_id, order_id, stale_minutes=STALE_FULFILLMENT_MINUTES)
    if not claim_id:
        logger.info(
            "Fulfillment skipped payment=%s order=%s (already fulfilled or being processed).",
            payment_id, order_id,
        )
        return None
    try:
        raw_token, token_hash = database.fulfill_payment(
            int(order["telegram_id"]), duration, order_id, payment_id, claim_id
        )
    except Exception as exc:
        attempts = whop_storage.record_fulfillment_failure(payment_id, str(exc)[:200])
        whop_storage.update_order(order_id, status="fulfillment_failed", payment_id=payment_id)
        logger.exception("Atomic fulfillment failed order=%s payment=%s attempts=%s", order_id, payment_id, attempts)
        raise FulfillmentRetryableError(
            f"Atomic fulfillment failed order={order_id} payment={payment_id}"
        )

    membership = payment.get("membership") or {}
    whop_storage.update_order(
        order_id,
        membership_id=str(membership.get("id") or "") or None,
    )
    logger.info(
        "Whop payment fulfilled payment=%s order=%s telegram=%s duration=%sd",
        payment_id,
        order_id,
        order["telegram_id"],
        duration,
    )
    return raw_token, duration, order_id


def _event_metadata(event_type: str, data: dict) -> tuple[dict, str | None, str | None]:
    metadata = data.get("metadata") or {}
    payment_id = str(data.get("id") or "") or None
    membership_id = None

    if event_type.startswith("refund."):
        payment = data.get("payment") or {}
        payment_id = str(payment.get("id") or payment_id or "") or None
        metadata = payment.get("metadata") or metadata
        membership = payment.get("membership") or {}
        membership_id = str(membership.get("id") or "") or None
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
        whop_storage.update_order(
            order_id, status="membership_deactivated", membership_id=membership_id
        )
        whop_storage.revoke_order_access(order_id)
    elif event_type == "membership.cancel_at_period_end_changed":
        whop_storage.update_order(
            order_id,
            status="cancel_at_period_end_changed",
            membership_id=membership_id,
        )
    elif event_type == "membership.activated":
        whop_storage.update_order(
            order_id, status="membership_active", membership_id=membership_id
        )
    return None


async def notify_customer(
    bot: Any, telegram_id: int, raw_token: str, duration_days: int, order_id: str
) -> None:
    lang = database.get_user_language(telegram_id)
    try:
        asset = visual_path("success")
        if asset:
            try:
                with open(asset, "rb") as fh:
                    await bot.send_photo(
                        chat_id=telegram_id,
                        photo=fh,
                        caption="<b>[ ACCESS ]: PAYMENT CONFIRMED</b>\n<i>NEURAL GOLD v3.2</i>",
                        parse_mode="HTML",
                    )
            except Exception:
                logger.exception("Premium payment visual delivery failed")
        await bot.send_message(
            chat_id=telegram_id,
            text=(
                "<b>[ SYSTEM ]: PAYMENT VERIFIED // FULFILLMENT COMPLETE</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                f"[ ACCESS ]: <b>{i18n.t(lang, 'access_now_active', days=duration_days)}</b>\n\n"
                f"{i18n.t(lang, 'auto_activated_note')}\n\n"
                ">> [ CORE ]: ALL INTELLIGENCE MODULES UNLOCKED. PRESS /start."
            ),
            parse_mode="HTML",
        )
        whop_storage.update_order(
            order_id,
            notified_at=datetime.now(timezone.utc),
            status="customer_notified",
        )
    except Exception as exc:
        logger.exception(
            "Failed to notify Telegram user %s for order %s: %s",
            telegram_id,
            order_id,
            exc,
        )
        whop_storage.update_order(order_id, status="active_notification_failed")


# ---------------------------------------------------------------------------
# Fulfillment ops (audit round-2): recovery worker + admin reconciliation
# ---------------------------------------------------------------------------

STALE_FULFILLMENT_MINUTES = 10
MAX_FULFILLMENT_ATTEMPTS = 3


def recover_stale_fulfillments(stale_minutes: int = STALE_FULFILLMENT_MINUTES,
                               max_attempts: int = MAX_FULFILLMENT_ATTEMPTS) -> dict:
    """Recovery worker: reclaim stale/failed claims and finish fulfillment.

    Returns a report dict:
      recovered  -> payment yang berhasil dipulihkan (user aktif)
      skipped    -> claim tidak bisa diambil (masih diproses worker lain)
      exhausted  -> attempts mencapai MAX -> butuh alert admin
    Normal Whop retry tetap berjalan seperti biasa; worker ini menutup celah
    'crash setelah claim' yang tidak akan pernah di-retry Whop.
    """
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
            report["recovered"].append({"payment_id": payment_id, "order_id": order_id,
                                        "telegram_id": order.get("telegram_id"), "duration_days": order.get("duration_days")})
            logger.info("Recovery worker fulfilled payment=%s order=%s", payment_id, order_id)
        except Exception as exc:
            attempts = whop_storage.record_fulfillment_failure(payment_id, str(exc)[:200])
            item = {"payment_id": payment_id, "order_id": order_id, "attempts": attempts,
                    "error": str(exc)[:160]}
            if attempts >= max_attempts:
                report["exhausted"].append(item)
            else:
                report["skipped"].append(payment_id)
            logger.warning("Recovery attempt failed payment=%s attempts=%s", payment_id, attempts)
    return report


def reconcile_payment(payment_id: str) -> dict:
    """Admin reconciliation: paksa pemeriksaan ulang satu payment (fenced)."""
    fulfillment = whop_storage.get_fulfillment(payment_id)
    order = whop_storage.get_order_by_payment(payment_id)
    if order is None and fulfillment:
        order = whop_storage.get_order(fulfillment["order_id"])
    if order is None:
        return {"ok": False, "reason": "ORDER/PAYMENT NOT FOUND"}

    if fulfillment and fulfillment.get("status") == "fulfilled":
        user = database.get_user_by_telegram_id(int(order["telegram_id"]))
        return {"ok": True, "status": "ALREADY FULFILLED",
                "telegram_id": order["telegram_id"],
                "expiry": user.subscription_expiry.isoformat() if user and user.subscription_expiry else None}

    claim_id = whop_storage.claim_fulfillment(payment_id, order["id"], stale_minutes=0)
    if not claim_id:
        return {"ok": False, "reason": "CLAIM GAGAL — sedang diproses worker lain, coba lagi nanti"}
    try:
        database.fulfill_payment(int(order["telegram_id"]), int(order["duration_days"]), order["id"], payment_id, claim_id)
        user = database.get_user_by_telegram_id(int(order["telegram_id"]))
        return {"ok": True, "status": "FULFILLED", "telegram_id": order["telegram_id"],
                "expiry": user.subscription_expiry.isoformat() if user and user.subscription_expiry else None}
    except Exception as exc:
        whop_storage.record_fulfillment_failure(payment_id, str(exc)[:200])
        return {"ok": False, "reason": str(exc)[:160]}


# ---------------------------------------------------------------------------
# Whop revalidation (Kelompok 1): recovery tanpa bergantung pada webhook delivery
# ---------------------------------------------------------------------------

import whop_api_phase2  # noqa: E402  (setelah definisi agar bebas circular import parsial)


async def reconcile_payment_remote(payment_id: str) -> dict:
    """Revalidasi via Whop API v2: tanya langsung status payment ke Whop.

    Dipakai ketika payment TIDAK ada di DB lokal (webhook hilang saat server
    crash/redeploy). Satu payment_id tetap maksimal satu fulfillment
    (whop_fulfillment lock + fencing claim_id berlaku sama).
    """
    payment = await whop_api_phase2.fetch_payment(payment_id)
    status = str(payment.get("status") or payment.get("substatus") or "").lower()
    if status not in ("paid", "succeeded"):
        return {"ok": False, "reason": f"WHOP_STATUS_{status.upper() or 'UNKNOWN'} (bukan pembayaran sukses)"}

    metadata = payment.get("metadata") or {}
    order_id = str(metadata.get("neural_order_id") or "") or f"ng_rec_{payment_id[-12:].lower()}"
    telegram_raw = str(metadata.get("telegram_id") or "")
    try:
        telegram_id = int(telegram_raw)
    except ValueError:
        return {"ok": False, "reason": "METADATA_TELEGRAM_ID_TIDAK_ADA — hubungi admin untuk aktivasi manual"}
    plan = payment.get("plan") or {}
    plan_id = str(plan.get("id") or "")
    try:
        days = int(metadata.get("plan_days") or 0)
    except ValueError:
        days = 0
    duration = days or PLAN_DURATIONS.get(plan_id, 30)
    membership_id = str((payment.get("membership") or {}).get("id") or "") or None

    if not whop_storage.get_order(order_id):
        if not whop_storage.create_order(order_id, telegram_id, plan_id or "unknown", duration):
            return {"ok": False, "reason": "GAGAL MEMBUAT ORDER LOKAL"}
    whop_storage.update_order(order_id, payment_id=payment_id, membership_id=membership_id)

    claim_id = whop_storage.claim_fulfillment(payment_id, order_id, stale_minutes=0)
    if not claim_id:
        return {"ok": True, "status": "ALREADY FULFILLED", "telegram_id": telegram_id}
    database.fulfill_payment(telegram_id, duration, order_id, payment_id, claim_id)
    return {"ok": True, "status": "FULFILLED VIA WHOP REVALIDATION",
            "telegram_id": telegram_id, "duration_days": duration}


async def reconcile_payment_full(payment_id: str) -> dict:
    """Urutan reconcile: DB lokal dulu -> revalidasi ke Whop API bila perlu."""
    local = reconcile_payment(payment_id)
    if local.get("ok"):
        return local
    local_reason = local.get("reason", "")
    if not payment_id.startswith("pay_"):
        return local
    remote = await reconcile_payment_remote(payment_id)
    if remote.get("ok"):
        return remote
    if "NOT_FOUND" in str(remote.get("reason", "")):
        return {"ok": False, "reason": f"{local_reason} | Whop: payment tidak ditemukan"}
    return {"ok": False, "reason": f"{local_reason} | Whop: {remote.get('reason', '')}"}
