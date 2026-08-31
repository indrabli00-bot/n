"""
database.py — SQLAlchemy ORM models and database operations.

Provides:
  - User model (profiles, subscription tokens, expiry)
  - UserSession model (per-user state cache to avoid redundant API calls)
  - TokenPool model (pre-generated tokens the admin can distribute)
  - All CRUD helpers used by auth.py and main.py

SQLite is used by default; switch to PostgreSQL by setting the
DATABASE_URL environment variable to a postgresql:// URI.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, create_engine, select, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import DATABASE_URL

logger = logging.getLogger(__name__)


def normalize_datetime_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(128), nullable=True)
    first_name = Column(String(128), nullable=True)
    language = Column(String(8), default="en", nullable=False)
    token = Column(String(256), nullable=True, index=True)
    is_active = Column(Boolean, default=False, nullable=False)
    subscription_expiry = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class UserSession(Base):
    __tablename__ = "user_sessions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    state = Column(String(64), default="idle", nullable=False)
    last_price_bid = Column(Float, nullable=True)
    last_price_ask = Column(Float, nullable=True)
    last_price_high = Column(Float, nullable=True)
    last_price_low = Column(Float, nullable=True)
    last_signal_time = Column(DateTime, nullable=True)
    last_fetch_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class TokenPool(Base):
    __tablename__ = "token_pool"
    id = Column(Integer, primary_key=True, autoincrement=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    duration_days = Column(Integer, default=30, nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    used_at = Column(DateTime, nullable=True)
    used_by_telegram_id = Column(Integer, nullable=True)


engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db() -> None:
    try:
        Base.metadata.create_all(bind=engine)
        if DATABASE_URL.startswith("sqlite"):
            from sqlalchemy import inspect, text
            inspector = inspect(engine)
            cols = {c["name"] for c in inspector.get_columns("users")}
            if "language" not in cols:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE users ADD COLUMN language VARCHAR(8) NOT NULL DEFAULT 'en'"))
                logger.info("Database migration applied: users.language")
        logger.info("Database tables initialised successfully.")
    except Exception as exc:
        logger.exception("Failed to initialise database tables: %s", exc)
        raise


def _get_session() -> Session:
    return SessionLocal()


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()


def get_user_by_telegram_id(telegram_id: int) -> User | None:
    session = _get_session()
    try:
        return session.scalar(select(User).where(User.telegram_id == telegram_id))
    except Exception as exc:
        logger.exception("get_user_by_telegram_id failed: %s", exc)
        return None
    finally:
        session.close()


def get_user_language(telegram_id: int) -> str:
    session = _get_session()
    try:
        user = session.scalar(select(User).where(User.telegram_id == telegram_id))
        return user.language if user and user.language else "en"
    except Exception as exc:
        logger.warning("get_user_language failed: %s", exc)
        return "en"
    finally:
        session.close()


def set_user_language(telegram_id: int, language: str) -> bool:
    session = _get_session()
    try:
        user = session.scalar(select(User).where(User.telegram_id == telegram_id))
        if user is None:
            return False
        user.language = language
        session.commit()
        return True
    except Exception as exc:
        session.rollback()
        logger.exception("set_user_language failed: %s", exc)
        return False
    finally:
        session.close()


def get_user_by_token(token: str) -> User | None:
    session = _get_session()
    try:
        return session.scalar(select(User).where(User.token == _hash_token(token)))
    except Exception as exc:
        logger.exception("get_user_by_token failed: %s", exc)
        return None
    finally:
        session.close()


def create_user(telegram_id: int, username: str | None, first_name: str | None, language: str = "en") -> User:
    session = _get_session()
    try:
        user = User(telegram_id=telegram_id, username=username, first_name=first_name, language=language, is_active=False)
        session.add(user)
        session.commit()
        session.refresh(user)
        logger.info("Created user %d (%s)", telegram_id, username or "no-username")
        return user
    except Exception as exc:
        session.rollback()
        logger.exception("create_user failed: %s", exc)
        raise
    finally:
        session.close()


def activate_user_token(telegram_id: int, raw_token: str, duration_days: int) -> bool:
    session = _get_session()
    try:
        token_hash = _hash_token(raw_token)
        pool_entry = session.scalar(select(TokenPool).where(TokenPool.token_hash == token_hash, TokenPool.is_used == False))  # noqa: E712
        if pool_entry is None:
            logger.warning("Token activation failed for user %d: token not found or already used.", telegram_id)
            return False

        pool_entry.is_used = True
        pool_entry.used_at = datetime.now(timezone.utc)
        pool_entry.used_by_telegram_id = telegram_id

        user = session.scalar(select(User).where(User.telegram_id == telegram_id))
        if user is None:
            user = User(telegram_id=telegram_id, is_active=False)
            session.add(user)
            session.flush()

        # Extend an existing active subscription instead of replacing unused time.
        now = datetime.now(timezone.utc)
        current_expiry = normalize_datetime_utc(user.subscription_expiry)
        base_time = current_expiry if user.is_active and current_expiry and current_expiry > now else now
        from datetime import timedelta
        user.token = token_hash
        user.is_active = True
        user.subscription_expiry = base_time + timedelta(days=duration_days)

        session.commit()
        logger.info("User %d activated token (expires %s).", telegram_id, user.subscription_expiry.isoformat())
        return True
    except Exception as exc:
        session.rollback()
        logger.exception("activate_user_token failed: %s", exc)
        return False
    finally:
        session.close()


def fulfill_payment(telegram_id: int, duration_days: int, order_id: str, payment_id: str, claim_id: str) -> tuple[str, str]:
    """Atomic Whop fulfillment WITH fencing (fulfillment ops).

    ONE transaction: create + consume the entitlement token, activate/extend
    the user, mark the order fulfilled-by-payment, and close the fulfillment
    lock — the lock update is FENCED by claim_id: a stale worker whose lease
    was taken over matches 0 rows and loses (rollback, no double credit).
    Returns (raw_token, token_hash).
    """
    raw_token = f"XAU-NEURAL-{secrets.token_hex(8).upper()}"
    token_hash = _hash_token(raw_token)
    now = datetime.now(timezone.utc)

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO token_pool (token_hash, duration_days, is_used, created_at, used_at, used_by_telegram_id)
                VALUES (:h, :d, 1, :now, :now, :tid)
            """),
            {"h": token_hash, "d": duration_days, "now": now, "tid": telegram_id},
        )
        user = conn.execute(
            text("SELECT is_active, subscription_expiry FROM users WHERE telegram_id = :tid"),
            {"tid": telegram_id},
        ).mappings().first()
        if user is None:
            new_expiry = now + timedelta(days=duration_days)
            conn.execute(
                text("""
                    INSERT INTO users (telegram_id, language, is_active, subscription_expiry, token, created_at, updated_at)
                    VALUES (:tid, :lang, 1, :exp, :h, :now, :now)
                """),
                {"tid": telegram_id, "lang": "en", "exp": new_expiry, "h": token_hash, "now": now},
            )
        else:
            current_raw = user["subscription_expiry"]
            if isinstance(current_raw, str):
                try:
                    current_raw = datetime.fromisoformat(current_raw)
                except ValueError:
                    current_raw = None
            current = normalize_datetime_utc(current_raw)
            base = current if user["is_active"] and current and current > now else now
            new_expiry = base + timedelta(days=duration_days)
            conn.execute(
                text("UPDATE users SET token = :h, is_active = 1, subscription_expiry = :exp, updated_at = :now WHERE telegram_id = :tid"),
                {"h": token_hash, "exp": new_expiry, "tid": telegram_id, "now": now},
            )
        order_row = conn.execute(
            text("UPDATE whop_orders SET payment_id = :pid, token_hash = :h, status = 'active', paid_at = :now, updated_at = :now WHERE id = :oid"),
            {"pid": payment_id, "h": token_hash, "now": now, "oid": order_id},
        )
        if order_row.rowcount != 1:
            raise RuntimeError(f"Fulfillment target order not found: {order_id}")
        lock_row = conn.execute(
            text("UPDATE whop_fulfillment SET status = 'fulfilled', updated_at = :now WHERE payment_id = :pid AND claim_id = :cid"),
            {"pid": payment_id, "cid": claim_id, "now": now},
        )
        if lock_row.rowcount != 1:
            raise RuntimeError(f"Fulfillment lease lost (stale claim fencing): payment={payment_id} claim={claim_id}")

    logger.info(
        "Atomic fulfillment complete telegram=%d order=%s payment=%s duration=%dd",
        telegram_id, order_id, payment_id, duration_days,
    )
    return raw_token, token_hash


def update_user(telegram_id: int, **kwargs) -> bool:
    session = _get_session()
    try:
        user = session.scalar(select(User).where(User.telegram_id == telegram_id))
        if user is None:
            return False
        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)
        session.commit()
        return True
    except Exception as exc:
        session.rollback()
        logger.exception("update_user failed: %s", exc)
        return False
    finally:
        session.close()


def add_token_to_pool(raw_token: str, duration_days: int = 30) -> bool:
    session = _get_session()
    try:
        session.add(TokenPool(token_hash=_hash_token(raw_token), duration_days=duration_days))
        session.commit()
        logger.info("Token added to pool (duration=%d days).", duration_days)
        return True
    except Exception as exc:
        session.rollback()
        logger.exception("add_token_to_pool failed: %s", exc)
        return False
    finally:
        session.close()


def list_all_users() -> list[dict]:
    session = _get_session()
    try:
        rows = session.scalars(select(User).order_by(User.id)).all()
        return [{"id": u.id, "telegram_id": u.telegram_id, "username": u.username, "first_name": u.first_name, "is_active": u.is_active, "subscription_expiry": u.subscription_expiry.isoformat() if u.subscription_expiry else None} for u in rows]
    except Exception as exc:
        logger.exception("list_all_users failed: %s", exc)
        return []
    finally:
        session.close()


def revoke_user(telegram_id: int) -> bool:
    return update_user(telegram_id, is_active=False, token=None)


def get_or_create_session(user_id: int) -> UserSession:
    session = _get_session()
    try:
        row = session.scalar(select(UserSession).where(UserSession.user_id == user_id))
        if row is not None:
            return row
        row = UserSession(user_id=user_id)
        session.add(row)
        session.commit()
        session.refresh(row)
        return row
    except Exception as exc:
        session.rollback()
        logger.exception("get_or_create_session failed: %s", exc)
        raise
    finally:
        session.close()


def update_session(user_id: int, **kwargs) -> None:
    session = _get_session()
    try:
        row = session.scalar(select(UserSession).where(UserSession.user_id == user_id))
        if row is None:
            return
        for key, value in kwargs.items():
            if hasattr(row, key):
                setattr(row, key, value)
        row.updated_at = datetime.now(timezone.utc)
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.exception("update_session failed: %s", exc)
    finally:
        session.close()
