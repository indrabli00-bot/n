import base64
import os
import unittest

os.environ.setdefault("WHOP_WEBHOOK_SECRET", "whsec_" + base64.b64encode(b"phase2-test-secret").decode().rstrip("="))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:TEST")

from whop_webhook_phase2 import verify_signature


class Phase2WebhookTests(unittest.TestCase):
    def test_standard_webhook_signature(self):
        import hashlib
        import hmac
        import json
        import time

        payload = json.dumps({"id": "msg_test", "type": "payment.succeeded", "data": {"id": "pay_test"}}, separators=(",", ":")).encode()
        webhook_id = "msg_test"
        timestamp = str(int(time.time()))
        signed = f"{webhook_id}.{timestamp}.".encode() + payload
        digest = base64.b64encode(
            hmac.new(b"phase2-test-secret", signed, hashlib.sha256).digest()
        ).decode()

        event = verify_signature(
            payload,
            {
                "webhook-id": webhook_id,
                "webhook-timestamp": timestamp,
                "webhook-signature": f"v1,{digest}",
            },
        )
        self.assertEqual(event["type"], "payment.succeeded")

    def test_invalid_signature_is_rejected(self):
        payload = b'{"type":"payment.succeeded","data":{}}'
        with self.assertRaises(ValueError):
            verify_signature(
                payload,
                {
                    "webhook-id": "msg_test",
                    "webhook-timestamp": "1",
                    "webhook-signature": "v1,invalid",
                },
            )


if __name__ == "__main__":
    unittest.main()
