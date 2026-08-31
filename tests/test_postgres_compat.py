from sqlalchemy import BigInteger

import database


def test_telegram_ids_use_64_bit_integer_storage():
    assert isinstance(database.User.__table__.c.telegram_id.type, BigInteger)
    assert isinstance(database.TokenPool.__table__.c.used_by_telegram_id.type, BigInteger)


def test_real_world_telegram_id_fits_model_type():
    telegram_id = 6_888_336_983
    assert telegram_id > 2_147_483_647
    assert isinstance(database.User.__table__.c.telegram_id.type, BigInteger)
