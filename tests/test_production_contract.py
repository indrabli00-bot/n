import asyncio
import inspect
import pathlib
import unittest
from unittest.mock import AsyncMock, patch


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ProductionContractTests(unittest.TestCase):
    def test_runtime_has_no_twelvedata_contract(self):
        targets = [
            ROOT / "app.py",
            ROOT / "api_handler.py",
            ROOT / "price_sources.py",
            ROOT / "market_candles.py",
            ROOT / "whop_api_phase2.py",
            ROOT / "whop_webhook_phase2.py",
        ]
        for path in targets:
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("TWELVEDATA_API_KEY", source, path.name)
            self.assertNotIn("api.twelvedata.com", source, path.name)

    def test_telegram_webhook_preserves_pending_updates(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("drop_pending_updates=False", source)
        self.assertNotIn("drop_pending_updates=True", source)

    def test_goldapi_sampler_uses_primary_goldapi_source(self):
        module = __import__("market_candles")
        with patch.object(module.price_sources, "fetch_goldapi", new=AsyncMock(return_value={"close": 3500.0})), patch.object(module, "record_sample") as record:
            self.assertTrue(asyncio.run(module.sample_goldapi()))
            record.assert_called_once_with(3500.0, source="GOLD_API")

    def test_candle_builder_rejects_unsupported_intervals(self):
        module = __import__("market_candles")
        self.assertIsNone(module.build_candles(1, 20))
        self.assertIsNone(module.get_candles("1min", 20))

    def test_notification_signature_is_minimal(self):
        module = __import__("whop_webhook_phase2")
        self.assertEqual(
            list(inspect.signature(module.notify_customer).parameters),
            ["bot", "telegram_id", "duration_days", "order_id"],
        )

    def test_whop_reconcile_uses_v1_payment_endpoint(self):
        module = __import__("whop_api_phase2")
        self.assertEqual(module.WHOP_API_BASE, "https://api.whop.com/api/v1")
        self.assertNotIn("/api/v2/", inspect.getsource(module.fetch_payment))

    def test_whop_success_accepts_paid_status_or_succeeded_substatus(self):
        module = __import__("whop_api_phase2")
        self.assertTrue(module._payment_is_successful({"status": "paid", "substatus": "pending"}))
        self.assertTrue(module._payment_is_successful({"status": "draft", "substatus": "succeeded"}))
        self.assertFalse(module._payment_is_successful({"status": "open", "substatus": "pending"}))


if __name__ == "__main__": unittest.main()
