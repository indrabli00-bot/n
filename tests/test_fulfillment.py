"""Fulfillment lock tests: payment_id idempotency + atomicity + stale recovery (claim_id API)."""
import base64
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:TEST")
os.environ.setdefault("GOLDAPI_API_KEY", "test-key")
os.environ.setdefault("WHOP_WEBHOOK_SECRET",
                      "whsec_" + base64.b64encode(b"phase2-test-secret").decode().rstrip("="))  # sama dengan test_phase2
os.environ.setdefault("WHOP_API_KEY", "test")

import database
import whop_storage
from sqlalchemy import text

database.init_db()
whop_storage.init_phase2_db()


def _consumed_tokens(telegram_id: int) -> int:
    with database.engine.begin() as conn:
        row = conn.execute(
            text("SELECT COUNT(*) AS c FROM token_pool WHERE used_by_telegram_id = :tid AND is_used = 1"),
            {"tid": telegram_id},
        ).mappings().first()
        return row["c"]


class FulfillmentLockTests(unittest.TestCase):
    def setUp(self):
        database.init_db()
        whop_storage.init_phase2_db()

    def test_01_claim_first_true_then_false(self):
        cid = whop_storage.claim_fulfillment("pay_c1", "o_c1")
        self.assertTrue(cid)
        self.assertIsNone(whop_storage.claim_fulfillment("pay_c1", "o_c1"))

    def test_02_atomic_fulfillment_success(self):
        whop_storage.create_order("o_b2", 101, "plan_ksl11weFJ0z41", 7)
        cid = whop_storage.claim_fulfillment("pay_b2", "o_b2")
        self.assertTrue(cid)
        raw, token_hash = database.fulfill_payment(101, 7, "o_b2", "pay_b2", cid)
        self.assertTrue(raw.startswith("XAU-NEURAL-"))
        order = whop_storage.get_order("o_b2")
        self.assertEqual(order["payment_id"], "pay_b2")
        self.assertEqual(order["token_hash"], token_hash)
        self.assertEqual(order["status"], "active")
        user = database.get_user_by_telegram_id(101)
        self.assertTrue(user.is_active)
        self.assertEqual(user.token, token_hash)
        self.assertIsNotNone(user.subscription_expiry)
        self.assertEqual(whop_storage.get_fulfillment("pay_b2")["status"], "fulfilled")

    def test_03_duplicate_event_same_payment_cannot_reextend(self):
        whop_storage.create_order("o_b3", 102, "plan_Yc1JnCIP8jgII", 14)
        cid = whop_storage.claim_fulfillment("pay_b3", "o_b3")
        database.fulfill_payment(102, 14, "o_b3", "pay_b3", cid)
        expiry_before = database.get_user_by_telegram_id(102).subscription_expiry
        self.assertIsNone(whop_storage.claim_fulfillment("pay_b3", "o_b3"))
        expiry_after = database.get_user_by_telegram_id(102).subscription_expiry
        self.assertEqual(expiry_before, expiry_after)
        self.assertEqual(_consumed_tokens(102), 1)

    def test_04_stale_processing_is_reclaimed_with_new_lease(self):
        stale = datetime.now(timezone.utc) - timedelta(minutes=11)
        with database.engine.begin() as conn:
            conn.execute(
                text("INSERT INTO whop_fulfillment (payment_id, order_id, status, claimed_at, updated_at) VALUES ('pay_b4', 'o_b4', 'processing', :c, :c)"),
                {"c": stale},
            )
        cid = whop_storage.claim_fulfillment("pay_b4", "o_b4", stale_minutes=10)
        self.assertTrue(cid)
        row = whop_storage.get_fulfillment("pay_b4")
        self.assertEqual(row["claim_id"], cid)

    def test_05_fresh_processing_is_not_reclaimed(self):
        fresh = datetime.now(timezone.utc)
        with database.engine.begin() as conn:
            conn.execute(
                text("INSERT INTO whop_fulfillment (payment_id, order_id, status, claimed_at, updated_at) VALUES ('pay_b5', 'o_b5', 'processing', :c, :c)"),
                {"c": fresh},
            )
        self.assertIsNone(whop_storage.claim_fulfillment("pay_b5", "o_b5", stale_minutes=10))

    def test_06_failed_can_retry(self):
        whop_storage.mark_fulfillment("pay_b6", "failed", "boom")
        self.assertTrue(whop_storage.claim_fulfillment("pay_b6", "o_b6", stale_minutes=10))

    def test_07_atomic_rollback_on_order_conflict(self):
        whop_storage.create_order("o_b7", 103, "plan_JDgh0geRuoSFX", 30)
        whop_storage.create_order("o_b8", 104, "plan_JDgh0geRuoSFX", 30)
        self.assertTrue(whop_storage.update_order("o_b8", payment_id="pay_bdup"))
        cid = whop_storage.claim_fulfillment("pay_bdup", "o_b7")
        with self.assertRaises(Exception):
            database.fulfill_payment(103, 30, "o_b7", "pay_bdup", cid)
        user = database.get_user_by_telegram_id(103)
        self.assertTrue(user is None or not user.is_active)
        self.assertEqual(_consumed_tokens(103), 0)
        self.assertEqual(whop_storage.get_fulfillment("pay_bdup")["status"], "processing")

    def test_08_webhook_delivery_dedup_unchanged(self):
        self.assertTrue(whop_storage.claim_webhook("ev_b1", "payment.succeeded", "pay_x"))
        self.assertFalse(whop_storage.claim_webhook("ev_b1", "payment.succeeded", "pay_x"))


if __name__ == "__main__":
    unittest.main()
