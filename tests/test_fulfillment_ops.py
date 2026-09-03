"""Failure-injection tests (fulfillment ops): fencing, recovery worker, multi-purchase, refund, notify.

Mencakup 10 skenario dari desain ops:
 1. same event retry
 2. same payment different event
 3. crash after claim -> recovery worker
 4. stale recovery
 5. fencing: worker A vs worker B
 6. slow worker after reclaim
 7. failed -> retry
 8. second legitimate purchase (cumulative extension)
 9. refund after second purchase (revoke tepat sasaran)
10. notification failure tidak mempengaruhi fulfillment
"""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:TEST")
os.environ.setdefault("GOLDAPI_API_KEY", "test-key")
os.environ.setdefault("WHOP_WEBHOOK_SECRET", "whsec_" + base64.b64encode(b"phase2-test-secret").decode().rstrip("="))
os.environ.setdefault("WHOP_API_KEY", "test")

import database
import whop_storage
import whop_webhook_phase2 as wh
from sqlalchemy import text

database.init_db()
whop_storage.init_phase2_db()


def _expiry(tid):
    u = database.get_user_by_telegram_id(tid)
    return u.subscription_expiry if u else None


class FulfillmentOpsTests(unittest.TestCase):
    def setUp(self):
        database.init_db()
        whop_storage.init_phase2_db()

    def test_same_event_retry_and_duplicate_event(self):
        whop_storage.create_order("ops_1", 201, "plan_ksl11weFJ0z41", 7)
        self.assertTrue(whop_storage.claim_webhook("ev_ops_1", "payment.succeeded", "pay_ops_1"))
        self.assertFalse(whop_storage.claim_webhook("ev_ops_1", "payment.succeeded", "pay_ops_1"))
        cid = whop_storage.claim_fulfillment("pay_ops_1", "ops_1")
        database.fulfill_payment(201, 7, "ops_1", "pay_ops_1", cid)
        exp1 = _expiry(201)
        self.assertTrue(whop_storage.claim_webhook("ev_ops_1b", "payment.succeeded", "pay_ops_1"))
        self.assertIsNone(whop_storage.claim_fulfillment("pay_ops_1", "ops_1"))
        self.assertEqual(_expiry(201), exp1)

    def test_recovery_worker_recovers_crashed_claim(self):
        whop_storage.create_order("ops_3", 202, "plan_Yc1JnCIP8jgII", 14)
        cid = whop_storage.claim_fulfillment("pay_ops_3", "ops_3")
        self.assertTrue(cid)
        report = wh.recover_stale_fulfillments(stale_minutes=0, max_attempts=3)
        self.assertTrue(any(r["payment_id"] == "pay_ops_3" for r in report["recovered"]))
        self.assertTrue(database.get_user_by_telegram_id(202).is_active)
        self.assertEqual(whop_storage.get_fulfillment("pay_ops_3")["status"], "fulfilled")

    def test_fencing_stale_worker_loses_lease(self):
        whop_storage.create_order("ops_5", 203, "plan_JDgh0geRuoSFX", 30)
        cid_a = whop_storage.claim_fulfillment("pay_ops_5", "ops_5", stale_minutes=0)
        self.assertTrue(cid_a)
        cid_b = whop_storage.claim_fulfillment("pay_ops_5", "ops_5", stale_minutes=0)
        self.assertTrue(cid_b and cid_b != cid_a)
        with self.assertRaises(Exception):
            database.fulfill_payment(203, 30, "ops_5", "pay_ops_5", cid_a)
        self.assertIsNone(_expiry(203))
        database.fulfill_payment(203, 30, "ops_5", "pay_ops_5", cid_b)
        self.assertTrue(database.get_user_by_telegram_id(203).is_active)

    def test_failed_then_retry_succeeds(self):
        whop_storage.create_order("ops_7", 204, "plan_ksl11weFJ0z41", 7)
        cid = whop_storage.claim_fulfillment("pay_ops_7", "ops_7", stale_minutes=0)
        whop_storage.record_fulfillment_failure("pay_ops_7", "transient")
        self.assertEqual(whop_storage.get_fulfillment("pay_ops_7")["status"], "failed")
        cid2 = whop_storage.claim_fulfillment("pay_ops_7", "ops_7", stale_minutes=0)
        self.assertTrue(cid2)
        database.fulfill_payment(204, 7, "ops_7", "pay_ops_7", cid2)
        self.assertTrue(database.get_user_by_telegram_id(204).is_active)

    def test_second_legitimate_purchase_extends(self):
        whop_storage.create_order("ops_8a", 205, "plan_ksl11weFJ0z41", 7)
        cid_a = whop_storage.claim_fulfillment("pay_ops_8a", "ops_8a", stale_minutes=0)
        database.fulfill_payment(205, 7, "ops_8a", "pay_ops_8a", cid_a)
        exp1 = _expiry(205)
        whop_storage.create_order("ops_8b", 205, "plan_Yc1JnCIP8jgII", 14)
        cid_b = whop_storage.claim_fulfillment("pay_ops_8b", "ops_8b", stale_minutes=0)
        database.fulfill_payment(205, 14, "ops_8b", "pay_ops_8b", cid_b)
        self.assertTrue(_expiry(205) > exp1)

    def test_refund_revokes_only_matching_order(self):
        whop_storage.create_order("ops_9a", 206, "plan_ksl11weFJ0z41", 7)
        cid_a = whop_storage.claim_fulfillment("pay_ops_9a", "ops_9a", stale_minutes=0)
        database.fulfill_payment(206, 7, "ops_9a", "pay_ops_9a", cid_a)
        whop_storage.create_order("ops_9b", 206, "plan_Yc1JnCIP8jgII", 14)
        cid_b = whop_storage.claim_fulfillment("pay_ops_9b", "ops_9b", stale_minutes=0)
        database.fulfill_payment(206, 14, "ops_9b", "pay_ops_9b", cid_b)
        self.assertFalse(whop_storage.revoke_order_access("ops_9a"))
        self.assertTrue(database.get_user_by_telegram_id(206).is_active)
        self.assertTrue(whop_storage.revoke_order_access("ops_9b"))
        self.assertFalse(database.get_user_by_telegram_id(206).is_active)

    def test_notify_failure_is_isolated(self):
        whop_storage.create_order("ops_10", 207, "plan_ksl11weFJ0z41", 7)
        cid = whop_storage.claim_fulfillment("pay_ops_10", "ops_10", stale_minutes=0)
        database.fulfill_payment(207, 7, "ops_10", "pay_ops_10", cid)
        class ExplodingBot:
            async def send_message(self, *a, **k): raise RuntimeError("network down")
            async def send_photo(self, *a, **k): raise RuntimeError("network down")
        asyncio.run(wh.notify_customer(ExplodingBot(), 207, 7, "ops_10"))
        self.assertTrue(database.get_user_by_telegram_id(207).is_active)
        self.assertEqual(whop_storage.get_fulfillment("pay_ops_10")["status"], "fulfilled")

    def test_recovery_exhausted_reports_alert_payload(self):
        whop_storage.create_order("ops_11", 208, "plan_Yc1JnCIP8jgII", 14)
        for _ in range(3):
            whop_storage.claim_fulfillment("pay_ops_11", "ops_11", stale_minutes=0)
            whop_storage.record_fulfillment_failure("pay_ops_11", "boom")
        report = wh.recover_stale_fulfillments(stale_minutes=0, max_attempts=3)
        self.assertFalse(any(r["payment_id"] == "pay_ops_11" for r in report["recovered"]))
        self.assertTrue(whop_storage.get_fulfillment("pay_ops_11")["attempts"] >= 3)

    def test_admin_queue_and_reconcile(self):
        whop_storage.create_order("ops_12", 209, "plan_JDgh0geRuoSFX", 30)
        whop_storage.claim_fulfillment("pay_ops_12", "ops_12", stale_minutes=0)
        q = whop_storage.fulfillment_queue()
        self.assertIn("processing", q["counts"])
        match = [r for r in q["rows"] if r["payment_id"] == "pay_ops_12"]
        self.assertTrue(match and match[0]["telegram_id"] == 209)
        result = wh.reconcile_payment("pay_ops_12")
        self.assertTrue(result["ok"] and result["status"] == "FULFILLED")
        self.assertTrue(database.get_user_by_telegram_id(209).is_active)
        again = wh.reconcile_payment("pay_ops_12")
        self.assertTrue(again["ok"] and again["status"] == "ALREADY FULFILLED")

    def test_ws_secret_variants(self):
        import time as _time
        payload = json.dumps({"type": "payment.succeeded", "data": {"id": "pay_ws"}}, separators=(",", ":")).encode()
        webhook_id, ts = "msg_ws", str(int(_time.time()))
        signed = f"{webhook_id}.{ts}.".encode() + payload
        full = "ws_" + "c" * 64
        stripped = full[3:]
        wrong = "ws_" + "d" * 64
        for secret, expect_ok in ((full, True), (stripped, True), (wrong, False)):
            digest = base64.b64encode(hmac.new(secret.encode(), signed, hashlib.sha256).digest()).decode()
            headers = {"webhook-id": webhook_id, "webhook-timestamp": ts, "webhook-signature": f"v1,{digest}"}
            with __import__("unittest").mock.patch.object(wh, "WHOP_WEBHOOK_SECRET", full):
                if expect_ok:
                    ev = wh.verify_signature(payload, headers)
                    self.assertEqual(ev["type"], "payment.succeeded")
                else:
                    with self.assertRaises(ValueError):
                        wh.verify_signature(payload, headers)
        digest = base64.b64encode(hmac.new(stripped.encode(), signed, hashlib.sha256).digest()).decode()
        headers = {"webhook-id": webhook_id, "webhook-timestamp": ts, "webhook-signature": f"v1,{digest}"}
        with __import__("unittest").mock.patch.object(wh, "WHOP_WEBHOOK_SECRET", stripped):
            ev = wh.verify_signature(payload, headers)
            self.assertEqual(ev["type"], "payment.succeeded")

    def test_remote_reconcile_via_whop_api(self):
        import whop_api_phase2
        payment = {"id": "pay_remote_1", "status": "paid", "metadata": {"neural_order_id": "ng_remote_1", "telegram_id": "210", "plan_days": "7", "source": "neural_gold"}, "plan": {"id": "plan_ksl11weFJ0z41"}, "membership": {"id": "mem_remote_1"}}
        orig = whop_api_phase2.fetch_payment
        async def _fake(pid): return payment
        whop_api_phase2.fetch_payment = _fake
        try: result = asyncio.run(wh.reconcile_payment_full("pay_remote_1"))
        finally: whop_api_phase2.fetch_payment = orig
        self.assertTrue(result["ok"], result)
        self.assertIn("REVALIDATION", result["status"])
        self.assertTrue(database.get_user_by_telegram_id(210).is_active)
        self.assertEqual(whop_storage.get_order("ng_remote_1")["payment_id"], "pay_remote_1")
        self.assertEqual(whop_storage.get_fulfillment("pay_remote_1")["status"], "fulfilled")

    def test_remote_reconcile_refuses_unpaid(self):
        import whop_api_phase2
        payment = {"id": "pay_remote_2", "status": "failed", "metadata": {"neural_order_id": "ng_remote_2", "telegram_id": "211"}, "plan": {"id": "plan_ksl11weFJ0z41"}}
        orig = whop_api_phase2.fetch_payment
        async def _fake(pid): return payment
        whop_api_phase2.fetch_payment = _fake
        try: result = asyncio.run(wh.reconcile_payment_full("pay_remote_2"))
        finally: whop_api_phase2.fetch_payment = orig
        self.assertFalse(result["ok"])
        self.assertIn("WHOP_STATUS_FAILED", result["reason"])
        self.assertIsNone(database.get_user_by_telegram_id(211))

    def test_remote_reconcile_duplicate_payment_fenced(self):
        import whop_api_phase2
        whop_storage.create_order("ops_r3", 212, "plan_ksl11weFJ0z41", 7)
        cid = whop_storage.claim_fulfillment("pay_r3", "ops_r3", stale_minutes=0)
        database.fulfill_payment(212, 7, "ops_r3", "pay_r3", cid)
        payment = {"id": "pay_r3", "status": "paid", "metadata": {"neural_order_id": "ops_r3", "telegram_id": "212"}, "plan": {"id": "plan_ksl11weFJ0z41"}}
        orig = whop_api_phase2.fetch_payment
        async def _fake(pid): return payment
        whop_api_phase2.fetch_payment = _fake
        try: result = asyncio.run(wh.reconcile_payment_full("pay_r3"))
        finally: whop_api_phase2.fetch_payment = orig
        self.assertTrue(result["ok"] and "ALREADY" in result["status"])
        exp = database.get_user_by_telegram_id(212).subscription_expiry
        result2 = asyncio.run(wh.reconcile_payment_full("pay_r3"))
        self.assertTrue(result2["ok"])
        self.assertEqual(database.get_user_by_telegram_id(212).subscription_expiry, exp)

    def test_webhook_self_heals_after_db_wipe(self):
        payment = {"id": "pay_wipe", "status": "paid", "metadata": {"neural_order_id": "ng_wiped_1", "telegram_id": "213", "plan_days": "7", "source": "neural_gold"}, "plan": {"id": "plan_ksl11weFJ0z41"}, "membership": {"id": "mem_w1"}}
        result = wh.handle_payment_succeeded(payment)
        self.assertTrue(result)
        raw_token, days, order_id = result
        self.assertEqual(order_id, "ng_wiped_1")
        self.assertEqual(whop_storage.get_order("ng_wiped_1")["payment_id"], "pay_wipe")
        self.assertTrue(database.get_user_by_telegram_id(213).is_active)
        self.assertEqual(whop_storage.get_fulfillment("pay_wipe")["status"], "fulfilled")

    def test_webhook_bad_metadata_is_retryable(self):
        payment = {"id": "pay_badmeta", "status": "paid", "metadata": {"neural_order_id": "ng_badmeta"}, "plan": {"id": "plan_ksl11weFJ0z41"}}
        with self.assertRaises(wh.FulfillmentRetryableError):
            wh.handle_payment_succeeded(payment)


if __name__ == "__main__":
    unittest.main()
