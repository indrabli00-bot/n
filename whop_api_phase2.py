"""Whop API helpers for Phase 2 per-user checkout sessions."""
from __future__ import annotations

import uuid
from typing import Any

import aiohttp

import whop_storage
from config import BELMO_PUBLIC_URL, WHOP_API_KEY, WHOP_COMPANY_ID

WHOP_API_BASE = "https://api.whop.com/api/v1"
PLAN_IDS = {
    7: "plan_ksl11weFJ0z41",
    14: "plan_Yc1JnCIP8jgII",
    30: "plan_JDgh0geRuoSFX",
}


def plan_id_for_days(days: int) -> str | None:
    return PLAN_IDS.get(days)


async def fetch_payment(payment_id: str) -> dict[str, Any]:
    """Fetch a payment from Whop v1 for remote reconciliation."""
    if not WHOP_API_KEY:
        raise RuntimeError("WHOP_API_KEY_not_configured")
    headers = {"Authorization": f"Bearer {WHOP_API_KEY}", "Accept": "application/json"}
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(
            f"{WHOP_API_BASE}/payments/{payment_id}", headers=headers
        ) as response:
            if response.status == 404:
                raise RuntimeError("payment_not_found_on_whop")
            response.raise_for_status()
            return await response.json(content_type=None)


def _payment_is_successful(payment: dict[str, Any]) -> bool:
    status = str(payment.get("status") or "").lower()
    substatus = str(payment.get("substatus") or "").lower()
    return status == "paid" or substatus == "succeeded"


async def create_checkout_for_user(
    telegram_id: int, duration_days: int
) -> tuple[str | None, str | None, str | None]:
    plan_id = plan_id_for_days(duration_days)
    if not plan_id:
        return None, None, "unsupported_plan"
    if not WHOP_API_KEY:
        return None, None, "WHOP_API_KEY_not_configured"

    order_id = f"ng_{uuid.uuid4().hex}"
    if not whop_storage.create_order(order_id, telegram_id, plan_id, duration_days):
        return None, None, "database_order_create_failed"

    # Whop's Checkout Configurations API accepts an existing plan through the
    # top-level `plan_id`. The company is scoped by the API key.
    payload = {
        "plan_id": plan_id,
        "mode": "payment",
        "metadata": {
            "neural_order_id": order_id,
            "telegram_id": str(telegram_id),
            "plan_days": str(duration_days),
            "source": "neural_gold",
        },
    }
    if BELMO_PUBLIC_URL:
        payload["redirect_url"] = f"{BELMO_PUBLIC_URL}/?checkout_status=success"

    headers = {
        "Authorization": f"Bearer {WHOP_API_KEY}",
        "Content-Type": "application/json",
        "Idempotency-Key": f"checkout-{order_id}",
    }
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{WHOP_API_BASE}/checkout_configurations",
                json=payload,
                headers=headers,
            ) as response:
                body = await response.json(content_type=None)
                if response.status >= 300:
                    whop_storage.update_order(order_id, status="checkout_failed")
                    if isinstance(body, dict):
                        detail = body.get("error") or body.get("message") or body
                    else:
                        detail = "request_failed"
                    return None, order_id, f"whop_http_{response.status}:{detail}"
                checkout_id = str(body.get("id") or "")
                purchase_url = str(body.get("purchase_url") or "")
                returned_plan_id = str((body.get("plan") or {}).get("id") or "")
                returned_company_id = str(body.get("company_id") or "")
                if returned_plan_id != plan_id:
                    whop_storage.update_order(order_id, status="checkout_failed")
                    return None, order_id, "whop_plan_mismatch_in_checkout_response"
                if WHOP_COMPANY_ID and returned_company_id and returned_company_id != WHOP_COMPANY_ID:
                    whop_storage.update_order(order_id, status="checkout_failed")
                    return None, order_id, "whop_company_mismatch_in_checkout_response"
                if not checkout_id or not purchase_url:
                    whop_storage.update_order(order_id, status="checkout_failed")
                    return None, order_id, "whop_missing_checkout_response"
                whop_storage.update_order(order_id, checkout_id=checkout_id, status="checkout_created")
                return purchase_url, order_id, None
    except Exception as exc:
        whop_storage.update_order(order_id, status="checkout_failed")
        return None, order_id, f"whop_request_failed:{type(exc).__name__}"
