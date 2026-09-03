"""Phase 2 Whop persistence using the existing SQLAlchemy engine."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

import database

logger = logging.getLogger("neural_gold.whop_storage")

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS whop_orders (
    id VARCHAR(64) PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    plan_id VARCHAR(128) NOT NULL,
    duration_days INTEGER NOT NULL,
    checkout_id VARCHAR(128) UNIQUE,
    payment_id VARCHAR(128) UNIQUE,
    membership_id VARCHAR(128),
    status VARCHAR(64) NOT NULL DEFAULT 'pending',
    token_hash VARCHAR(64),
    created_at TIMESTAMP NOT NULL,
    paid_at TIMESTAMP,
    notified_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_whop_orders_telegram_id ON whop_orders(telegram_id);
CREATE INDEX IF NOT EXISTS ix_whop_orders_plan_id ON whop_orders(plan_id);
CREATE INDEX IF NOT EXISTS ix_whop_orders_payment_id ON whop_orders(payment_id);
CREATE INDEX IF NOT EXISTS ix_whop_orders_membership_id ON whop_orders(membership_id);
CREATE INDEX IF NOT EXISTS ix_whop_orders_status ON whop_orders(status);
CREATE TABLE IF NOT EXISTS whop_webhook_events (
    id VARCHAR(128) PRIMARY KEY,
    event_type VARCHAR(128) NOT NULL,
    payment_id VARCHAR(128),
    status VARCHAR(32) NOT NULL DEFAULT 'received',
    created_at TIMESTAMP NOT NULL,
    processed_at TIMESTAMP,
    error_message VARCHAR(1000)
);
CREATE INDEX IF NOT EXISTS ix_whop_webhook_events_event_type ON whop_webhook_events(event_type);
CREATE INDEX IF NOT EXISTS ix_whop_webhook_events_payment_id ON whop_webhook_events(payment_id);
CREATE INDEX IF NOT EXISTS ix_whop_webhook_events_status ON whop_webhook_events(status);
CREATE TABLE IF NOT EXISTS whop_fulfillment (
    payment_id VARCHAR(128) PRIMARY KEY,
    order_id VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'processing',
    claim_id VARCHAR(64),
    attempts INTEGER NOT NULL DEFAULT 0,
    claimed_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    error_message VARCHAR(500)
);
CREATE INDEX IF NOT EXISTS ix_whop_fulfillment_status ON whop_fulfillment(status);
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def init_phase2_db() -> None:
    with database.engine.begin() as conn:
        for statement in CREATE_SQL.split(";"):
            statement = statement.strip()
            if statement:
                conn.execute(text(statement))
    migrations = [
        "ALTER TABLE whop_fulfillment ADD COLUMN claim_id VARCHAR(64)",
        "ALTER TABLE whop_fulfillment ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0",
    ]
    if database.engine.dialect.name == "postgresql":
        migrations.append("ALTER TABLE whop_orders ALTER COLUMN telegram_id TYPE BIGINT")
    for migration in migrations:
        try:
            with database.engine.begin() as conn:
                conn.execute(text(migration))
        except Exception:
            pass
    logger.info("Whop Phase 2 tables initialised.")


def create_order(order_id: str, telegram_id: int, plan_id: str, duration_days: int) -> bool:
    now = _now()
    try:
        with database.engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO whop_orders
                (id, telegram_id, plan_id, duration_days, status, created_at, updated_at)
                VALUES (:id, :telegram_id, :plan_id, :duration_days, 'pending', :created_at, :updated_at)
                ON CONFLICT (id) DO NOTHING
            """), {"id": order_id, "telegram_id": telegram_id, "plan_id": plan_id,
                  "duration_days": duration_days, "created_at": now, "updated_at": now})
            return result.rowcount == 1
    except Exception:
        logger.exception("Failed to create Whop order %s", order_id)
        return False


def update_order(order_id: str, **fields) -> bool:
    allowed = {"checkout_id", "payment_id", "membership_id", "status", "token_hash", "paid_at", "notified_at"}
    values = {k: v for k, v in fields.items() if k in allowed}
    if not values:
        return False
    values["updated_at"] = _now()
    assignments = ", ".join(f"{key} = :{key}" for key in values)
    values["id"] = order_id
    try:
        with database.engine.begin() as conn:
            result = conn.execute(text(f"UPDATE whop_orders SET {assignments} WHERE id = :id"), values)
            return result.rowcount == 1
    except Exception:
        logger.exception("Failed to update Whop order %s", order_id)
        return False


def get_order(order_id: str) -> dict | None:
    with database.engine.begin() as conn:
        row = conn.execute(text("SELECT * FROM whop_orders WHERE id = :id"), {"id": order_id}).mappings().first()
        return dict(row) if row else None


def get_order_by_payment(payment_id: str) -> dict | None:
    with database.engine.begin() as conn:
        row = conn.execute(text("SELECT * FROM whop_orders WHERE payment_id = :payment_id"), {"payment_id": payment_id}).mappings().first()
        return dict(row) if row else None


def get_order_by_membership(membership_id: str) -> dict | None:
    with database.engine.begin() as conn:
        row = conn.execute(text("SELECT * FROM whop_orders WHERE membership_id = :membership_id"), {"membership_id": membership_id}).mappings().first()
        return dict(row) if row else None


def list_unnotified_orders(min_age_seconds: int = 90, limit: int = 50) -> list[dict]:
    """Return active orders whose customer notification is still pending."""
    cutoff = _now() - timedelta(seconds=min_age_seconds)
    try:
        with database.engine.begin() as conn:
            rows = conn.execute(text("""
                SELECT id, telegram_id, duration_days, payment_id, status, notified_at, updated_at
                FROM whop_orders
                WHERE notified_at IS NULL
                  AND status IN ('active', 'active_notification_failed')
                  AND updated_at <= :cutoff
                ORDER BY updated_at ASC
                LIMIT :limit
            """), {"cutoff": cutoff, "limit": limit}).mappings().all()
            return [dict(r) for r in rows]
    except Exception:
        logger.exception("list_unnotified_orders failed")
        return []


def claim_webhook(event_id: str, event_type: str, payment_id: str | None = None) -> bool:
    now = _now()
    try:
        with database.engine.begin() as conn:
            inserted = conn.execute(text("""
                INSERT INTO whop_webhook_events
                (id, event_type, payment_id, status, created_at)
                VALUES (:id, :event_type, :payment_id, 'processing', :created_at)
                ON CONFLICT (id) DO NOTHING
            """), {"id": event_id, "event_type": event_type, "payment_id": payment_id, "created_at": now})
            if inserted.rowcount == 1:
                return True
            reclaimed = conn.execute(text("""
                UPDATE whop_webhook_events
                SET status = 'processing', processed_at = NULL, error_message = NULL
                WHERE id = :id AND status IN ('failed', 'received')
            """), {"id": event_id})
            return reclaimed.rowcount == 1
    except Exception:
        logger.exception("Failed to claim Whop webhook %s", event_id)
        return False


def mark_webhook(event_id: str, status: str, error_message: str | None = None) -> None:
    with database.engine.begin() as conn:
        conn.execute(text("""
            UPDATE whop_webhook_events
            SET status = :status, processed_at = :processed_at, error_message = :error_message
            WHERE id = :id
        """), {"id": event_id, "status": status, "processed_at": _now(), "error_message": error_message})


def get_fulfillment(payment_id: str) -> dict | None:
    with database.engine.begin() as conn:
        row = conn.execute(text("SELECT * FROM whop_fulfillment WHERE payment_id = :pid"), {"pid": payment_id}).mappings().first()
        return dict(row) if row else None


def mark_fulfillment(payment_id: str, status: str, error_message: str | None = None) -> None:
    try:
        with database.engine.begin() as conn:
            conn.execute(text("""
                UPDATE whop_fulfillment SET status = :status, updated_at = :now,
                    error_message = COALESCE(:err, error_message)
                WHERE payment_id = :pid
            """), {"pid": payment_id, "status": status, "now": _now(), "err": error_message})
    except Exception:
        logger.exception("mark_fulfillment failed payment=%s", payment_id)


def claim_fulfillment(payment_id: str, order_id: str, stale_minutes: int = 10) -> str | None:
    claim_id = uuid.uuid4().hex
    now = _now()
    cutoff = now - timedelta(minutes=stale_minutes)
    try:
        with database.engine.begin() as conn:
            row = conn.execute(text("SELECT status FROM whop_fulfillment WHERE payment_id = :pid"), {"pid": payment_id}).mappings().first()
            if row is None:
                conn.execute(text("""
                    INSERT INTO whop_fulfillment (payment_id, order_id, status, claim_id, claimed_at, updated_at)
                    VALUES (:pid, :oid, 'processing', :cid, :now, :now)
                """), {"pid": payment_id, "oid": order_id, "cid": claim_id, "now": now})
                return claim_id
            status = row["status"]
            if status == "fulfilled":
                return None
            if status == "failed":
                updated = conn.execute(text("""
                    UPDATE whop_fulfillment SET status='processing', claim_id=:cid, claimed_at=:now, updated_at=:now
                    WHERE payment_id=:pid AND status='failed'
                """), {"pid": payment_id, "cid": claim_id, "now": now})
                return claim_id if updated.rowcount == 1 else None
            if status in ("processing", "pending"):
                reclaimed = conn.execute(text("""
                    UPDATE whop_fulfillment SET status='processing', claim_id=:cid, claimed_at=:now, updated_at=:now
                    WHERE payment_id=:pid AND status=:st AND claimed_at <= :cutoff
                """), {"pid": payment_id, "cid": claim_id, "now": now, "st": status, "cutoff": cutoff})
                return claim_id if reclaimed.rowcount == 1 else None
            return None
    except Exception:
        logger.exception("claim_fulfillment failed payment=%s", payment_id)
        return None


def record_fulfillment_failure(payment_id: str, error_message: str) -> int:
    try:
        with database.engine.begin() as conn:
            row = conn.execute(text("""
                UPDATE whop_fulfillment SET status='failed', attempts=attempts+1,
                    error_message=:err, updated_at=:now
                WHERE payment_id=:pid RETURNING attempts
            """), {"pid": payment_id, "err": error_message[:500], "now": _now()}).mappings().first()
            return int(row["attempts"]) if row else 0
    except Exception:
        logger.exception("record_fulfillment_failure failed payment=%s", payment_id)
        return -1


def list_stale_claims(stale_minutes: int = 10, max_attempts: int = 3) -> list[dict]:
    cutoff = _now() - timedelta(minutes=stale_minutes)
    try:
        with database.engine.begin() as conn:
            rows = conn.execute(text("""
                SELECT payment_id, order_id, status, attempts, claimed_at, updated_at
                FROM whop_fulfillment
                WHERE (status='processing' AND claimed_at <= :cutoff)
                   OR (status='failed' AND attempts < :max_attempts)
                ORDER BY claimed_at ASC LIMIT 50
            """), {"cutoff": cutoff, "max_attempts": max_attempts}).mappings().all()
            return [dict(r) for r in rows]
    except Exception:
        logger.exception("list_stale_claims failed")
        return []


def fulfillment_queue(limit: int = 20) -> dict:
    try:
        with database.engine.begin() as conn:
            counts = {r["status"]: r["c"] for r in conn.execute(text("SELECT status, COUNT(*) AS c FROM whop_fulfillment GROUP BY status")).mappings().all()}
            rows = conn.execute(text("""
                SELECT f.payment_id, f.order_id, f.status, f.attempts, f.claimed_at, o.telegram_id, o.duration_days
                FROM whop_fulfillment f LEFT JOIN whop_orders o ON o.id=f.order_id
                WHERE f.status != 'fulfilled' ORDER BY f.claimed_at DESC LIMIT :limit
            """), {"limit": limit}).mappings().all()
            return {"counts": counts, "rows": [dict(r) for r in rows]}
    except Exception:
        logger.exception("fulfillment_queue failed")
        return {"counts": {}, "rows": []}


def recent_orders_for(telegram_id: int, limit: int = 3) -> list[dict]:
    try:
        with database.engine.begin() as conn:
            rows = conn.execute(text("""
                SELECT id, status, duration_days, payment_id, created_at
                FROM whop_orders WHERE telegram_id=:tid ORDER BY created_at DESC LIMIT :limit
            """), {"tid": telegram_id, "limit": limit}).mappings().all()
            return [dict(r) for r in rows]
    except Exception:
        logger.exception("recent_orders_for failed tid=%s", telegram_id)
        return []


def revoke_order_access(order_id: str) -> bool:
    order = get_order(order_id)
    if not order or not order.get("token_hash"):
        return False
    user = database.get_user_by_telegram_id(int(order["telegram_id"]))
    if user is None or user.token != order["token_hash"]:
        return False
    return database.update_user(int(order["telegram_id"]), is_active=False)
