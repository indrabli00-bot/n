import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ['DATABASE_URL'] = 'sqlite:///./test_entitlement.sqlite'
os.environ['WHOP_PRODUCT_ID'] = 'prod_neural_gold'
os.environ['WHOP_COMPANY_ID'] = 'biz_neural_gold'
os.environ['WHOP_WEBHOOK_SECRET'] = 'whsec_test'
os.environ['WHOP_OAUTH_STATE_SECRET'] = 'state_test'
os.environ['ADMIN_TELEGRAM_ID'] = '999'

from sqlalchemy import select

import database
from app import process_whop


def setup_module():
    database.Base.metadata.create_all(database.engine)
    database.init_db()


def teardown_module():
    try:
        Path('test_entitlement.sqlite').unlink()
    except FileNotFoundError:
        pass


def test_telegram_update_is_claimed_once():
    update_id = 900001
    database.release_telegram_update(update_id)

    assert database.claim_telegram_update(update_id) is True
    assert database.claim_telegram_update(update_id) is False

    database.complete_telegram_update(update_id)
    assert database.claim_telegram_update(update_id) is False
    database.release_telegram_update(update_id)


def test_failed_telegram_update_can_be_retried():
    update_id = 900002
    database.release_telegram_update(update_id)

    assert database.claim_telegram_update(update_id) is True
    database.release_telegram_update(update_id)
    assert database.claim_telegram_update(update_id) is True
    database.release_telegram_update(update_id)

