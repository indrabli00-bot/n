"""Runtime safety hardening for payment and access-control paths.

This module is deliberately small and installed once during Belmo startup.
It closes race/crash-recovery gaps without duplicating the application flow.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import wraps
import logging

from sqlalchemy import inspect, text

import database
import whop_api_phase2
import whop_storage
import whop_webhook_phase2

logger = logging.getLogger("neural_gold.hardening")

_REQUIRED_PHASE2_COLUMNS = {
    "whop_orders": {"telegram_id", "duration_days", "payment_id", "token_hash"},
    "whop_webhook_events": {"id", "status", "processed_at"},
    "whop_fulfillment": {"payment_id", "order_id", "status", "claim_id", "attempts"},
}


def _atomic_activate_user_token(telegram_id: int, raw_token: str, duration_days: int) -> bool:
    """Atomically burn a token before granting access."""
    token_hash = database._hash_token(raw_token)
    now = datetime.now(timezone.utc)
    try:
        with database.engine.begin() as conn:
            claimed = conn.execute(
                text("""
                    UPDATE token_pool
                    SET is_used = TRUE, used_at = :now, used_by_telegram_id = :telegram_id
                    WHERE token_hash = :token_hash AND is_used = FALSE
                    RETURNING duration_days
                """),
                {"now": now, "telegram_id": telegram_id, "token_hash": token_hash},
            ).mappings().first()
            if claimed is None:
                return False

            effective_days = int(claimed["duration_days"] or duration_days)
            user = conn.execute(
                text("SELECT is_active, subscription_expiry FROM users WHERE telegram_id = :telegram_id"),
                {"telegram_id": telegram_id},
            ).mappings().first()

            if user is None:
                expiry = now + timedelta(days=effective_days)
                conn.execute(
                    text("""
                        INSERT INTO users
                        (telegram_id, is_active, subscription_expiry, token, created_at, updated_at)
                        VALUES (:telegram_id, TRUE, :expiry, :token_hash, :now, :now)
                    """),
                    {"telegram_id": telegram_id, "expiry": expiry, "token_hash": token_hash, "now": now},
                )
            else:
                current = database.normalize_datetime_utc(user["subscription_expiry"])
                base = current if user["is_active"] and current and current > now else now
                expiry = base + timedelta(days=effective_days)
                conn.execute(
                    text("""
                        UPDATE users
                        SET token = :token_hash, is_active = TRUE,
                            subscription_expiry = :expiry, updated_at = :now
                        WHERE telegram_id = :telegram_id
                    """),
                    {"token_hash": token_hash, "expiry": expiry, "now": now, "telegram_id": telegram_id},
                )
        return True
    except Exception:
        logger.exception("Atomic token activation failed telegram_id=%s", telegram_id)
        return False


def _claim_webhook_with_stale_recovery(event_id: str, event_type: str, payment_id: str | None = None) -> bool:
    """Claim a webhook and recover abandoned processing claims safely.

    Database failures are raised instead of being converted to ``False``.
    ``False`` therefore means only that the event is already claimed/processed,
    while infrastructure failure reaches the HTTP handler and gets a retryable 5xx.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=5)
    try:
        with database.engine.begin() as conn:
            inserted = conn.execute(
                text("""
                    INSERT INTO whop_webhook_events
                    (id, event_type, payment_id, status, created_at, processed_at)
                    VALUES (:id, :event_type, :payment_id, 'processing', :created_at, :claimed_at)
                    ON CONFLICT (id) DO NOTHING
                """),
                {"id": event_id, "event_type": event_type, "payment_id": payment_id,
                 "created_at": now, "claimed_at": now},
            )
            if inserted.rowcount == 1:
                return True

            reclaimed = conn.execute(
                text("""
                    UPDATE whop_webhook_events
                    SET status = 'processing', processed_at = :claimed_at,
                        error_message = NULL
                    WHERE id = :id
                      AND (
                          status IN ('failed', 'received')
                          OR (status = 'processing' AND (processed_at IS NULL OR processed_at <= :cutoff))
                      )
                """),
                {"id": event_id, "claimed_at": now, "cutoff": cutoff},
            )
            return reclaimed.rowcount == 1
    except Exception:
        logger.exception("Webhook claim failed event=%s", event_id)
        raise


def _validate_remote_payment_plan(payment: dict) -> dict:
    """Validate Whop plan identity before remote reconciliation can grant access."""
    plan = payment.get("plan") or {}
    plan_id = str(plan.get("id") or "")
    expected_days = whop_webhook_phase2.PLAN_DURATIONS.get(plan_id)
    if expected_days is None:
        raise whop_webhook_phase2.FulfillmentRetryableError(
            f"Unknown Whop plan_id: {plan_id!r}; refusing remote fulfillment"
        )

    metadata = payment.get("metadata") or {}
    raw_days = metadata.get("plan_days")
    if raw_days not in (None, ""):
        try:
            metadata_days = int(raw_days)
        except (TypeError, ValueError) as exc:
            raise whop_webhook_phase2.FulfillmentRetryableError(
                f"Invalid metadata.plan_days for plan {plan_id!r}"
            ) from exc
        if metadata_days != expected_days:
            raise whop_webhook_phase2.FulfillmentRetryableError(
                f"Plan duration mismatch for {plan_id!r}: metadata={metadata_days}, expected={expected_days}"
            )
    return payment


def _validate_phase2_schema() -> None:
    inspector = inspect(database.engine)
    tables = set(inspector.get_table_names())
    missing_tables = set(_REQUIRED_PHASE2_COLUMNS) - tables
    if missing_tables:
        raise RuntimeError(f"Phase 2 schema missing tables: {sorted(missing_tables)}")
    for table, required in _REQUIRED_PHASE2_COLUMNS.items():
        columns = {column["name"] for column in inspector.get_columns(table)}
        missing = required - columns
        if missing:
            raise RuntimeError(f"Phase 2 schema missing columns in {table}: {sorted(missing)}")


class _StrictPlanDurations(dict):
    """Reject unknown plans instead of granting implicit access."""

    def get(self, key, default=None):  # type: ignore[override]
        if key in self:
            return super().get(key)
        if default == 30:
            raise whop_webhook_phase2.FulfillmentRetryableError(
                f"Unknown Whop plan_id: {key!r}; refusing implicit 30-day access"
            )
        return default


def install() -> None:
    """Install hardening patches exactly once."""
    if getattr(database, "_neural_gold_hardening_installed", False):
        return

    database.activate_user_token = _atomic_activate_user_token
    whop_storage.claim_webhook = _claim_webhook_with_stale_recovery

    original_init = whop_storage.init_phase2_db

    @wraps(original_init)
    def init_phase2_db_hardened() -> None:
        original_init()
        _validate_phase2_schema()

    whop_storage.init_phase2_db = init_phase2_db_hardened
    whop_webhook_phase2.PLAN_DURATIONS = _StrictPlanDurations(whop_webhook_phase2.PLAN_DURATIONS)

    original_fetch_payment = whop_api_phase2.fetch_payment

    @wraps(original_fetch_payment)
    async def fetch_payment_validated(payment_id: str) -> dict:
        payment = await original_fetch_payment(payment_id)
        return _validate_remote_payment_plan(payment)

    whop_api_phase2.fetch_payment = fetch_payment_validated
    database._neural_gold_hardening_installed = True
