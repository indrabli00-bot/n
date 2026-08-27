"""Whop API helpers for Phase 2 per-user checkout sessions."""
from __future__ import annotations

import uuid

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


async def create_checkout_for_user(
    telegram_id: int, duration_days: int
) -> tuple[str | None, str | None, str | None]:
    plan_id = plan_id_for_days(duration_days)
    if not plan_id:
        return None, None, "unsupported_plan"
    if not WHOP_API_KEY:
        return None, None, "WHOP_API_KEY_not_configured"
    if not WHOP_COMPANY_ID:
        return None, None, "WHOP_COMPANY_ID_not_configured"

    order_id = f"ng_{uuid.uuid4().hex}"
    if not whop_storage.create_order(order_id, telegram_id, plan_id, duration_days):
        return None, None, "database_order_create_failed"

    headers = {
        "Authorization": f"Bearer {WHOP_API_KEY}",
        "Content-Type": "application/json",
        "Idempotency-Key": f"checkout-{order_id}",
    }

    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Whop's current API creates a checkout configuration from a plan
            # object. Read the selected plan first so its exact price, product,
            # billing model, and expiration settings are preserved.
            async with session.get(
                f"{WHOP_API_BASE}/plans/{plan_id}",
                headers=headers,
            ) as plan_response:
                plan_body = await plan_response.json(content_type=None)
                if plan_response.status >= 300 or not isinstance(plan_body, dict):
                    whop_storage.update_order(order_id, status="checkout_failed")
                    detail = plan_body.get("error") if isinstance(plan_body, dict) else "plan_lookup_failed"
                    return None, order_id, f"whop_plan_http_{plan_response.status}:{detail}"

            company = plan_body.get("company") or {}
            product = plan_body.get("product") or {}
            plan_company_id = str(company.get("id") or "")
            product_id = str(product.get("id") or "")
            if plan_company_id and plan_company_id != WHOP_COMPANY_ID:
                whop_storage.update_order(order_id, status="checkout_failed")
                return None, order_id, "plan_company_mismatch"
            if not product_id:
                whop_storage.update_order(order_id, status="checkout_failed")
                return None, order_id, "plan_product_missing"

            plan_payload = {
                "company_id": WHOP_COMPANY_ID,
                "product_id": product_id,
                "title": plan_body.get("title") or f"NEURAL GOLD {duration_days} DAYS",
                "description": plan_body.get("description"),
                "initial_price": plan_body.get("initial_price"),
                "renewal_price": plan_body.get("renewal_price"),
                "billing_period": plan_body.get("billing_period"),
                "expiration_days": plan_body.get("expiration_days"),
                "plan_type": plan_body.get("plan_type"),
                "release_method": plan_body.get("release_method") or "buy_now",
                "visibility": plan_body.get("visibility") or "visible",
                "trial_period_days": plan_body.get("trial_period_days"),
                "force_create_new_plan": False,
            }
            plan_payload = {key: value for key, value in plan_payload.items() if value is not None}

            payload = {
                "plan": plan_payload,
                "mode": "payment",
                "metadata": {
                    "neural_order_id": order_id,
                    "telegram_id": str(telegram_id),
                    "plan_days": str(duration_days),
                    "source": "neural_gold",
                },
            }
            if BELMO_PUBLIC_URL:
                payload["redirect_url"] = f"{BELMO_PUBLIC_URL}/"

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
                if not checkout_id or not purchase_url:
                    whop_storage.update_order(order_id, status="checkout_failed")
                    return None, order_id, "whop_missing_checkout_response"
                whop_storage.update_order(order_id, checkout_id=checkout_id, status="checkout_created")
                return purchase_url, order_id, None
    except Exception as exc:
        whop_storage.update_order(order_id, status="checkout_failed")
        return None, order_id, f"whop_request_failed:{type(exc).__name__}"
