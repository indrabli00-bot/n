"""Verify a PostgreSQL DATABASE_URL and initialize the NEURAL GOLD schema.

Usage:
    DATABASE_URL='postgresql+psycopg://...' python scripts/verify_postgres.py

The script never prints the connection URL or password.
"""
from __future__ import annotations

import os
import sys

from sqlalchemy import inspect, text

# Allow execution from repository root and from the scripts directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import engine, init_db  # noqa: E402

EXPECTED_TABLES = {
    "users",
    "user_sessions",
    "token_pool",
    "whop_orders",
    "whop_fulfillment",
    "whop_webhook_events",
}


def main() -> int:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url.startswith(("postgresql://", "postgresql+psycopg://")):
        print("ERROR: DATABASE_URL must be a PostgreSQL URL (postgresql:// or postgresql+psycopg://).")
        return 2

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        init_db()
        tables = set(inspect(engine).get_table_names())
    except Exception as exc:
        print(f"ERROR: PostgreSQL connection/schema check failed: {exc}")
        return 1

    missing = EXPECTED_TABLES - tables
    if missing:
        print(f"ERROR: missing tables: {sorted(missing)}")
        return 1

    print("OK: PostgreSQL connection succeeded and NEURAL GOLD schema is present.")
    print("Tables:", ", ".join(sorted(EXPECTED_TABLES)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
