from __future__ import annotations
from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from config import DATABASE_URL

url = DATABASE_URL.replace('postgres://', 'postgresql+psycopg://', 1).replace('postgresql://', 'postgresql+psycopg://', 1)
engine = create_engine(url, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

class Base(DeclarativeBase): pass

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    subscription_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Order(Base):
    __tablename__ = 'orders'
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    plan_id: Mapped[str] = mapped_column(String(80))
    duration_days: Mapped[int] = mapped_column(Integer)
    payment_id: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    membership_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    checkout_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default='created')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class MarketSample(Base):
    __tablename__ = 'market_samples'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), unique=True, index=True)
    price: Mapped[float] = mapped_column(Float)
    change_pct: Mapped[float] = mapped_column(Float, default=0.0)

class Fulfillment(Base):
    __tablename__ = 'fulfillments'
    payment_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    order_id: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(30), default='pending')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

def init_db() -> None: Base.metadata.create_all(engine)

def get_user(telegram_id: int) -> User | None:
    with SessionLocal() as s: return s.scalar(select(User).where(User.telegram_id == telegram_id))

def ensure_user(telegram_id: int) -> User:
    with SessionLocal() as s:
        u = s.scalar(select(User).where(User.telegram_id == telegram_id))
        if not u:
            u = User(telegram_id=telegram_id); s.add(u); s.commit(); s.refresh(u)
        return u

def activate_subscription(telegram_id: int, days: int) -> datetime:
    now = datetime.now(timezone.utc)
    with SessionLocal() as s:
        u = s.scalar(select(User).where(User.telegram_id == telegram_id)) or User(telegram_id=telegram_id)
        base = u.subscription_expiry if u.subscription_expiry and u.subscription_expiry > now else now
        if base.tzinfo is None: base = base.replace(tzinfo=timezone.utc)
        u.subscription_expiry = base + timedelta(days=days); u.is_active = True
        s.add(u); s.commit(); s.refresh(u); return u.subscription_expiry

def deactivate_subscription(telegram_id: int) -> None:
    with SessionLocal() as s:
        u = s.scalar(select(User).where(User.telegram_id == telegram_id))
        if u: u.is_active = False; s.commit()

def revoke_subscription(telegram_id: int) -> None:
    with SessionLocal() as s:
        u = s.scalar(select(User).where(User.telegram_id == telegram_id))
        if u:
            u.is_active = False
            u.subscription_expiry = datetime.now(timezone.utc)
            s.commit()

def save_sample(price: float, change_pct: float, ts: datetime | None = None) -> None:
    ts = ts or datetime.now(timezone.utc)
    with SessionLocal() as s:
        if not s.scalar(select(MarketSample).where(MarketSample.ts == ts)):
            s.add(MarketSample(ts=ts, price=price, change_pct=change_pct)); s.commit()

def recent_samples(limit: int = 600) -> list[dict]:
    with SessionLocal() as s:
        rows = s.scalars(select(MarketSample).order_by(MarketSample.ts.desc()).limit(limit)).all()
        return [{'ts': r.ts, 'price': r.price, 'change_pct': r.change_pct} for r in reversed(rows)]

def create_order(order_id: str, telegram_id: int, plan_id: str, days: int) -> bool:
    with SessionLocal() as s:
        if s.get(Order, order_id): return True
        s.add(Order(id=order_id, telegram_id=telegram_id, plan_id=plan_id, duration_days=days)); s.commit(); return True

def update_order(order_id: str, **fields) -> None:
    with SessionLocal() as s:
        o = s.get(Order, order_id)
        if o:
            for k, v in fields.items(): setattr(o, k, v)
            s.commit()

def get_order(order_id: str) -> Order | None:
    with SessionLocal() as s: return s.get(Order, order_id)

def get_order_by_payment(payment_id: str) -> Order | None:
    with SessionLocal() as s: return s.scalar(select(Order).where(Order.payment_id == payment_id))

def fulfill(payment_id: str, order_id: str) -> bool:
    with SessionLocal() as s:
        f = s.get(Fulfillment, payment_id)
        if f and f.status == 'fulfilled': return False
        o = s.get(Order, order_id)
        if not o: raise RuntimeError('order_not_found')
        if o.payment_id and o.payment_id != payment_id: raise RuntimeError('order_payment_mismatch')
        u = s.scalar(select(User).where(User.telegram_id == o.telegram_id)) or User(telegram_id=o.telegram_id)
        now = datetime.now(timezone.utc)
        base = u.subscription_expiry if u.subscription_expiry and u.subscription_expiry > now else now
        if base.tzinfo is None: base = base.replace(tzinfo=timezone.utc)
        u.subscription_expiry = base + timedelta(days=o.duration_days); u.is_active = True
        o.payment_id = payment_id; o.status = 'fulfilled'
        if not f: f = Fulfillment(payment_id=payment_id, order_id=order_id)
        f.status = 'fulfilled'; f.attempts = (f.attempts or 0) + 1
        s.add_all([u, o, f]); s.commit(); return True
