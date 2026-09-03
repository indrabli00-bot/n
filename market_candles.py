"""GoldAPI-derived intraday candle builder for NEURAL GOLD v3.2.

GoldAPI.io exposes live spot prices and daily historical prices, not native M5/M15
candles. This module therefore builds honest intraday bars from timestamped live
GoldAPI spot samples. No synthetic backfill is created: missing coverage keeps
NEURAL STRIKES in DATA_GAP/HOLD until enough real samples exist.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

import database
import price_sources

logger = logging.getLogger("neural_gold.market_candles")
SAMPLE_INTERVAL_SECONDS = 60
RETENTION_HOURS = 72
_MIN_COVERAGE = {5: 3, 15: 9}

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS market_price_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sampled_at TIMESTAMP NOT NULL,
    price FLOAT NOT NULL,
    source VARCHAR(64) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_market_price_samples_sampled_at ON market_price_samples(sampled_at);
"""


def init_db() -> None:
    with database.engine.begin() as conn:
        for statement in CREATE_SQL.split(";"):
            statement = statement.strip()
            if statement:
                conn.execute(text(statement))
    logger.info("Market candle sample storage initialised.")


def record_sample(price: float, sampled_at: datetime | None = None, source: str = "GOLD_API") -> None:
    value = float(price)
    if value <= 0:
        raise ValueError("price must be positive")
    ts = sampled_at or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ts = ts.astimezone(timezone.utc)
    with database.engine.begin() as conn:
        conn.execute(
            text("INSERT INTO market_price_samples (sampled_at, price, source) VALUES (:ts, :price, :source)"),
            {"ts": ts, "price": value, "source": source},
        )
        cutoff = ts - timedelta(hours=RETENTION_HOURS)
        conn.execute(text("DELETE FROM market_price_samples WHERE sampled_at < :cutoff"), {"cutoff": cutoff})


async def sample_goldapi() -> bool:
    """Capture one live GoldAPI sample; failures never affect the Telegram path."""
    try:
        price = await price_sources.fetch_goldapi()
        record_sample(float(price["close"]), source="GOLD_API")
        return True
    except Exception as exc:
        logger.warning("GoldAPI candle sample failed: %s", exc)
        return False


def _bucket_start(ts: datetime, minutes: int) -> datetime:
    epoch = int(ts.timestamp())
    bucket = epoch - (epoch % (minutes * 60))
    return datetime.fromtimestamp(bucket, tz=timezone.utc)


def build_candles(interval_minutes: int, outputsize: int = 100) -> list[dict] | None:
    if interval_minutes not in (5, 15) or outputsize < 1:
        return None
    now = datetime.now(timezone.utc)
    current_bucket = _bucket_start(now, interval_minutes)
    needed_buckets = outputsize
    lookback = timedelta(minutes=interval_minutes * (needed_buckets + 2))
    cutoff = current_bucket - lookback
    with database.engine.begin() as conn:
        rows = conn.execute(
            text("""
                SELECT sampled_at, price FROM market_price_samples
                WHERE sampled_at >= :cutoff AND sampled_at < :current_bucket
                ORDER BY sampled_at ASC
            """),
            {"cutoff": cutoff, "current_bucket": current_bucket},
        ).mappings().all()

    buckets: dict[datetime, list[tuple[datetime, float]]] = {}
    for row in rows:
        ts = row["sampled_at"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts = ts.astimezone(timezone.utc)
        buckets.setdefault(_bucket_start(ts, interval_minutes), []).append((ts, float(row["price"])))

    minimum = _MIN_COVERAGE[interval_minutes]
    complete: list[dict] = []
    bucket = cutoff + timedelta(minutes=interval_minutes)
    while bucket < current_bucket:
        samples = buckets.get(bucket)
        if samples and len(samples) >= minimum:
            values = [value for _, value in samples]
            complete.append({
                "time": bucket.isoformat(),
                "open": values[0],
                "high": max(values),
                "low": min(values),
                "close": values[-1],
            })
        bucket += timedelta(minutes=interval_minutes)

    if len(complete) < outputsize:
        return None
    return complete[-outputsize:]


def get_candles(interval: str, outputsize: int = 100) -> list[dict] | None:
    mapping = {"5min": 5, "15min": 15}
    minutes = mapping.get(str(interval).lower())
    if minutes is None:
        return None
    return build_candles(minutes, outputsize)


async def collect_job() -> None:
    await sample_goldapi()


def schedule(scheduler) -> None:
    scheduler.add_job(
        collect_job,
        "interval",
        seconds=SAMPLE_INTERVAL_SECONDS,
        max_instances=1,
        coalesce=True,
        id="goldapi_market_sample",
        replace_existing=True,
    )
    logger.info("GoldAPI intraday sampler scheduled every %ds.", SAMPLE_INTERVAL_SECONDS)
