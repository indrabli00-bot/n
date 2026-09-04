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


def test_membership_lifecycle_and_renewal_window():
    database.ensure_user(123)
    database.link_whop_user(123, 'user_1')
    database.apply_membership_event('evt_1', 'membership.activated', 'mem_1', 'user_1', 'active', datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(days=30), 'prod_neural_gold')
    assert database.membership_active(123) is True
    database.apply_membership_event('evt_2', 'membership.deactivated', 'mem_1', 'user_1', 'inactive', None, None, 'prod_neural_gold')
    assert database.membership_active(123) is False


def test_expired_active_membership_has_no_access():
    database.ensure_user(125)
    database.link_whop_user(125, 'user_expired')
    database.apply_membership_event('evt_expired', 'membership.activated', 'mem_expired', 'user_expired', 'active', None, datetime.now(timezone.utc) - timedelta(seconds=1), 'prod_neural_gold')
    assert database.membership_active(125) is False


def test_other_product_cannot_grant_access():
    database.ensure_user(126)
    database.link_whop_user(126, 'user_other_product')
    database.apply_membership_event('evt_other_product', 'membership.activated', 'mem_other_product', 'user_other_product', 'active', None, datetime.now(timezone.utc) + timedelta(days=30), 'prod_other')
    assert database.membership_active(126) is False


def test_recurring_membership_update_replaces_whop_period():
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    first_end = datetime(2026, 10, 1, tzinfo=timezone.utc)
    next_end = datetime(2026, 11, 1, tzinfo=timezone.utc)
    database.apply_membership_event('evt_recurring_1', 'membership.activated', 'mem_recurring', 'user_recurring', 'active', start, first_end, 'prod_neural_gold')
    database.apply_membership_event('evt_recurring_2', 'membership.activated', 'mem_recurring', 'user_recurring', 'active', first_end, next_end, 'prod_neural_gold')
    with database.SessionLocal() as s:
        row = s.scalar(select(database.WhopMembership).where(database.WhopMembership.membership_id == 'mem_recurring'))
    assert row is not None
    actual_end = row.renewal_period_end
    if actual_end and actual_end.tzinfo is None:
        actual_end = actual_end.replace(tzinfo=timezone.utc)
    assert actual_end == next_end


def test_webhook_idempotency():
    payload = {
        '_webhook_id': 'evt_idempotent',
        'type': 'membership.activated',
        'company_id': 'biz_neural_gold',
        'data': {
            'id': 'mem_idempotent',
            'user': {'id': 'user_idempotent'},
            'status': 'active',
            'renewal_period_start': '2026-09-01T00:00:00Z',
            'renewal_period_end': '2026-10-01T00:00:00Z',
            'product': {'id': 'prod_neural_gold'},
        },
    }
    asyncio.run(process_whop(payload))
    asyncio.run(process_whop(payload))
    with database.SessionLocal() as s:
        events = s.scalars(select(database.WebhookEvent).where(database.WebhookEvent.event_id == 'evt_idempotent')).all()
        memberships = s.scalars(select(database.WhopMembership).where(database.WhopMembership.membership_id == 'mem_idempotent')).all()
    assert len(events) == 1
    assert len(memberships) == 1


def test_failed_membership_write_is_retryable():
    payload = {
        '_webhook_id': 'evt_retryable',
        'type': 'membership.activated',
        'company_id': 'biz_neural_gold',
        'data': {
            'id': 'mem_retryable',
            'user': {'id': 'user_retryable'},
            'status': 'active',
            'renewal_period_start': '2026-09-01T00:00:00Z',
            'renewal_period_end': '2026-10-01T00:00:00Z',
            'product': {'id': 'prod_neural_gold'},
        },
    }
    original = database.apply_membership_event
    calls = {'count': 0}

    def fail_once(*args):
        calls['count'] += 1
        if calls['count'] == 1:
            raise RuntimeError('temporary_failure')
        return original(*args)

    database.apply_membership_event = fail_once
    try:
        try:
            asyncio.run(process_whop(payload))
        except RuntimeError:
            pass
        asyncio.run(process_whop(payload))
    finally:
        database.apply_membership_event = original

    with database.SessionLocal() as s:
        event = s.get(database.WebhookEvent, 'evt_retryable')
        membership = s.scalar(select(database.WhopMembership).where(database.WhopMembership.membership_id == 'mem_retryable'))
    assert event is not None
    assert membership is not None


def test_payment_succeeded_cannot_create_entitlement():
    payload = {'_webhook_id': 'evt_payment', 'type': 'payment.succeeded', 'company_id': 'biz_neural_gold', 'data': {'id': 'pay_1'}}
    asyncio.run(process_whop(payload))
    with database.SessionLocal() as s:
        assert s.get(database.WebhookEvent, 'evt_payment') is None


def test_membership_updated_to_canceled_removes_access():
    database.ensure_user(124)
    database.link_whop_user(124, 'user_cancel')
    database.apply_membership_event('evt_cancel_active', 'membership.activated', 'mem_cancel', 'user_cancel', 'active', None, None, 'prod_neural_gold')
    assert database.membership_active(124) is True
    payload = {
        '_webhook_id': 'evt_cancel_update',
        'type': 'membership.updated',
        'company_id': 'biz_neural_gold',
        'data': {'id': 'mem_cancel', 'user': {'id': 'user_cancel'}, 'status': 'canceled', 'product': {'id': 'prod_neural_gold'}},
    }
    asyncio.run(process_whop(payload))
    assert database.membership_active(124) is False


def test_membership_webhook_requires_product_id():
    payload = {
        '_webhook_id': 'evt_missing_product',
        'type': 'membership.activated',
        'company_id': 'biz_neural_gold',
        'data': {'id': 'mem_missing_product', 'user': {'id': 'user_missing_product'}, 'status': 'active'},
    }
    try:
        asyncio.run(process_whop(payload))
    except ValueError as exc:
        assert str(exc) == 'membership_product_missing'
    else:
        raise AssertionError('missing product_id must be rejected')


def test_stale_membership_event_cannot_reactivate_access():
    newer = datetime(2026, 9, 5, 12, tzinfo=timezone.utc)
    older = datetime(2026, 9, 5, 11, tzinfo=timezone.utc)
    database.apply_membership_event('evt_newer', 'membership.updated', 'mem_ordered', 'user_ordered', 'canceled', None, None, 'prod_neural_gold', newer)
    database.apply_membership_event('evt_older', 'membership.updated', 'mem_ordered', 'user_ordered', 'active', None, newer + timedelta(days=30), 'prod_neural_gold', older)
    with database.SessionLocal() as s:
        row = s.scalar(select(database.WhopMembership).where(database.WhopMembership.membership_id == 'mem_ordered'))
    assert row is not None
    assert row.status == 'canceled'
