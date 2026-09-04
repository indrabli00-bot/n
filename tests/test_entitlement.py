import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ['DATABASE_URL'] = 'sqlite:///./test_entitlement.sqlite'
os.environ['WHOP_PRODUCT_ID'] = 'prod_neural_gold'
os.environ['WHOP_COMPANY_ID'] = 'biz_neural_gold'
os.environ['WHOP_WEBHOOK_SECRET'] = 'whsec_test'
os.environ['WHOP_OAUTH_STATE_SECRET'] = 'state_test'

import database
from app import process_whop


def setup_module():
    database.Base.metadata.create_all(database.engine)


def teardown_module():
    try: Path('test_entitlement.sqlite').unlink()
    except FileNotFoundError: pass


def test_membership_lifecycle_and_renewal_window():
    database.ensure_user(123)
    database.link_whop_user(123, 'user_1')
    database.sync_membership('mem_1', 'user_1', 'active', datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(days=30), 'prod_neural_gold')
    assert database.membership_active(123) is True
    database.deactivate_membership('mem_1', 'canceled')
    assert database.membership_active(123) is False


def test_recurring_membership_update_replaces_whop_period():
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    first_end = datetime(2026, 10, 1, tzinfo=timezone.utc)
    next_end = datetime(2026, 11, 1, tzinfo=timezone.utc)
    database.sync_membership('mem_recurring', 'user_recurring', 'active', start, first_end, 'prod_neural_gold')
    database.sync_membership('mem_recurring', 'user_recurring', 'active', first_end, next_end, 'prod_neural_gold')
    row = database.SessionLocal().get(database.WhopMembership, 2)
    assert row is not None and row.renewal_period_end == next_end


def test_webhook_idempotency(monkeypatch):
    seen = set(); sync_calls = []
    def record(event_id, event_type):
        if event_id in seen: return False
        seen.add(event_id); return True
    monkeypatch.setattr(database, 'record_webhook_event', record)
    monkeypatch.setattr(database, 'sync_membership', lambda *args: sync_calls.append(args))
    payload = {'_webhook_id': 'evt_1', 'type': 'membership.activated', 'company_id': 'biz_neural_gold', 'data': {'id': 'mem_2', 'user': {'id': 'user_2'}, 'status': 'active', 'renewal_period_start': '2026-09-01T00:00:00Z', 'renewal_period_end': '2026-10-01T00:00:00Z', 'product': {'id': 'prod_neural_gold'}}}
    asyncio.run(process_whop(payload)); asyncio.run(process_whop(payload))
    assert len(sync_calls) == 1


def test_payment_succeeded_cannot_create_entitlement(monkeypatch):
    called = []
    monkeypatch.setattr(database, 'record_webhook_event', lambda *args: True)
    monkeypatch.setattr(database, 'sync_membership', lambda *args: called.append(True))
    payload = {'_webhook_id': 'evt_payment', 'type': 'payment.succeeded', 'company_id': 'biz_neural_gold', 'data': {'id': 'pay_1'}}
    asyncio.run(process_whop(payload))
    assert called == []
