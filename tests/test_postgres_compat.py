from pathlib import Path

from sqlalchemy import BigInteger

import database


def test_telegram_ids_use_64_bit_integer_storage():
    assert isinstance(database.User.__table__.c.telegram_id.type, BigInteger)
    assert isinstance(database.UserSession.__table__.c.user_id.type, BigInteger)
    assert isinstance(database.TokenPool.__table__.c.used_by_telegram_id.type, BigInteger)


def test_real_world_telegram_id_fits_model_type():
    telegram_id = 6_888_336_983
    assert telegram_id > 2_147_483_647
    assert isinstance(database.User.__table__.c.telegram_id.type, BigInteger)
    assert isinstance(database.UserSession.__table__.c.user_id.type, BigInteger)


def test_postgres_migration_includes_session_telegram_ids():
    source = Path(database.__file__).read_text(encoding="utf-8")
    assert '"user_sessions": ("user_id",)' in source


def test_atomic_fulfillment_uses_postgres_boolean_literals():
    source = Path(database.__file__).read_text(encoding="utf-8")
    assert "VALUES (:h, :d, TRUE, :now, :now, :tid)" in source
    assert "SET token = :h, is_active = TRUE" in source
    assert "VALUES (:h, :d, 1, :now, :now, :tid)" not in source
    assert "SET token = :h, is_active = 1" not in source
