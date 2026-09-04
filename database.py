from __future__ import annotations
from datetime import datetime, timezone
import json
from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text, create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from config import DATABASE_URL, WHOP_PRODUCT_ID

url = DATABASE_URL.replace('postgres://', 'postgresql+psycopg://', 1).replace('postgresql://', 'postgresql+psycopg://', 1)
engine = create_engine(url, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

class Base(DeclarativeBase): pass

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    whop_user_id: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class WhopMembership(Base):
    __tablename__ = 'whop_memberships'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    membership_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    whop_user_id: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(50), index=True)
    renewal_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    renewal_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    product_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class WebhookEvent(Base):
    __tablename__ = 'webhook_events'
    event_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class OAuthState(Base):
    __tablename__ = 'oauth_states'
    state: Mapped[str] = mapped_column(String(160), primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    code_verifier: Mapped[str] = mapped_column(String(200))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

class MarketSample(Base):
    __tablename__ = 'market_samples'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), unique=True, index=True)
    price: Mapped[float] = mapped_column(Float)
    change_pct: Mapped[float] = mapped_column(Float, default=0.0)

class ApprovedSignal(Base):
    __tablename__ = 'approved_signals'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[str] = mapped_column(Text)
    approved_by: Mapped[int] = mapped_column(BigInteger, index=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

def init_db() -> None:
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    users_columns = {column['name'] for column in inspector.get_columns('users')}
    if 'whop_user_id' not in users_columns:
        with engine.begin() as conn:
            conn.execute(text('ALTER TABLE users ADD COLUMN whop_user_id VARCHAR(120)'))
        inspector = inspect(engine)
        user_indexes = {index['name'] for index in inspector.get_indexes('users')}
        if 'ix_users_whop_user_id' not in user_indexes:
            with engine.begin() as conn:
                conn.execute(text('CREATE UNIQUE INDEX ix_users_whop_user_id ON users (whop_user_id)'))
    membership_columns = {column['name'] for column in inspector.get_columns('whop_memberships')}
    if 'product_id' not in membership_columns:
        with engine.begin() as conn:
            conn.execute(text('ALTER TABLE whop_memberships ADD COLUMN product_id VARCHAR(120)'))

def db_ping() -> bool:
    with engine.connect() as conn: conn.execute(text('SELECT 1'))
    return True

def latest_sample() -> dict | None:
    with SessionLocal() as s:
        r = s.scalar(select(MarketSample).order_by(MarketSample.ts.desc()).limit(1))
        return {'ts': r.ts, 'price': r.price} if r else None

def get_user(telegram_id: int) -> User | None:
    with SessionLocal() as s: return s.scalar(select(User).where(User.telegram_id == telegram_id))

def ensure_user(telegram_id: int) -> User:
    with SessionLocal() as s:
        u = s.scalar(select(User).where(User.telegram_id == telegram_id))
        if not u:
            u = User(telegram_id=telegram_id); s.add(u); s.commit(); s.refresh(u)
        return u

def link_whop_user(telegram_id: int, whop_user_id: str) -> None:
    with SessionLocal() as s:
        u = s.scalar(select(User).where(User.telegram_id == telegram_id)) or User(telegram_id=telegram_id)
        conflict = s.scalar(select(User).where(User.whop_user_id == whop_user_id, User.telegram_id != telegram_id))
        if conflict: raise ValueError('whop_user_already_linked')
        u.whop_user_id = whop_user_id
        s.add(u); s.commit()

def save_oauth_state(state: str, telegram_id: int, code_verifier: str, expires_at: datetime) -> None:
    with SessionLocal() as s:
        s.add(OAuthState(state=state, telegram_id=telegram_id, code_verifier=code_verifier, expires_at=expires_at)); s.commit()

def consume_oauth_state(state: str) -> OAuthState | None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as s:
        row = s.get(OAuthState, state)
        if not row: return None
        expiry = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
        if expiry <= now:
            s.delete(row); s.commit(); return None
        s.delete(row); s.commit(); return row

def apply_membership_event(event_id: str, event_type: str, membership_id: str, whop_user_id: str, status: str, renewal_start: datetime | None, renewal_end: datetime | None, product_id: str) -> bool:
    with SessionLocal() as s:
        if s.get(WebhookEvent, event_id): return False
        membership = s.scalar(select(WhopMembership).where(WhopMembership.membership_id == membership_id))
        if not membership:
            membership = WhopMembership(membership_id=membership_id, whop_user_id=whop_user_id, status=status)
        membership.whop_user_id = whop_user_id
        membership.status = status
        membership.renewal_period_start = renewal_start
        membership.renewal_period_end = renewal_end
        membership.product_id = product_id
        membership.updated_at = datetime.now(timezone.utc)
        s.add(membership)
        s.add(WebhookEvent(event_id=event_id, event_type=event_type))
        try:
            s.commit()
        except IntegrityError:
            s.rollback()
            if s.get(WebhookEvent, event_id): return False
            raise
        return True

def get_membership_for_telegram(telegram_id: int) -> WhopMembership | None:
    with SessionLocal() as s:
        u = s.scalar(select(User).where(User.telegram_id == telegram_id))
        if not u or not u.whop_user_id: return None
        return s.scalar(
            select(WhopMembership)
            .where(
                WhopMembership.whop_user_id == u.whop_user_id,
                WhopMembership.product_id == WHOP_PRODUCT_ID,
            )
            .order_by(WhopMembership.updated_at.desc())
            .limit(1)
        )

def membership_active(telegram_id: int) -> bool:
    m = get_membership_for_telegram(telegram_id)
    if not m or m.status != 'active': return False
    if m.renewal_period_end is None: return True
    expiry = m.renewal_period_end if m.renewal_period_end.tzinfo else m.renewal_period_end.replace(tzinfo=timezone.utc)
    return expiry > datetime.now(timezone.utc)

def save_approved_signal(payload: dict, approved_by: int) -> None:
    with SessionLocal() as s:
        s.add(ApprovedSignal(payload=json.dumps(payload, separators=(',', ':'), sort_keys=True), approved_by=approved_by)); s.commit()

def latest_approved_signal() -> dict | None:
    with SessionLocal() as s:
        row = s.scalar(select(ApprovedSignal).order_by(ApprovedSignal.approved_at.desc(), ApprovedSignal.id.desc()).limit(1))
        return json.loads(row.payload) if row else None

def save_sample(price: float, change_pct: float, ts: datetime | None = None) -> None:
    ts = ts or datetime.now(timezone.utc)
    with SessionLocal() as s:
        if not s.scalar(select(MarketSample).where(MarketSample.ts == ts)):
            s.add(MarketSample(ts=ts, price=price, change_pct=change_pct)); s.commit()

def recent_samples(limit: int = 600) -> list[dict]:
    with SessionLocal() as s:
        rows = s.scalars(select(MarketSample).order_by(MarketSample.ts.desc()).limit(limit)).all()
        return [{'ts': r.ts, 'price': r.price, 'change_pct': r.change_pct} for r in reversed(rows)]
