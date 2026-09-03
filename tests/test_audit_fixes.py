import asyncio
import importlib
import unittest
from unittest.mock import AsyncMock, patch


class AuditFixTests(unittest.TestCase):
    def test_smc_trade_levels_use_structure_and_scale_targets_from_risk(self):
        smc = importlib.import_module("smc_engine")
        candles = []
        for i in range(70):
            close = 3000.0 + i * 0.15
            candles.append({"open": close - 0.4, "high": close + 0.6, "low": close - 0.8, "close": close})
        candles[62] = {"open": 3009.0, "high": 3009.4, "low": 2998.0, "close": 3000.0}
        candles[63] = {"open": 3000.0, "high": 3004.0, "low": 2999.0, "close": 3003.0}
        candles[-1]["close"] = 3010.0
        levels = smc._build_trade_levels(candles, "BUY", 3010.0)
        self.assertIsNotNone(levels)
        entry_low, entry_high, tp1, tp2, tp3, sl, basis = levels
        displayed_risk = round(tp1 - 3010.0, 2)
        self.assertGreater(displayed_risk, 0)
        self.assertEqual(tp2, round(3010.0 + 2 * displayed_risk, 2))
        self.assertEqual(tp3, round(3010.0 + 3 * displayed_risk, 2))
        self.assertLess(sl, entry_low)
        self.assertEqual(basis, "STRUCTURE/ATR")

    def test_smc_signal_accepts_live_reference_price(self):
        smc = importlib.import_module("smc_engine")
        candles = []
        for i in range(100):
            base = 3000.0 + i * 0.2
            candles.append({"open": base - 0.2, "high": base + 0.8, "low": base - 0.8, "close": base + 0.2})
        signal = smc.generate_signal(candles, candles, reference_price=3055.5)
        self.assertEqual(signal["signal_price"], 3055.5)
        self.assertEqual(signal["signal_price_source"], "LIVE_REFERENCE")

    def test_api_passes_live_bid_as_signal_reference(self):
        api = importlib.import_module("api_handler")
        captured = {}

        async def fake_signal(reference_price=None):
            captured["price"] = reference_price
            return {"direction": "HOLD", "confidence": 0, "entry_low": 0.0, "entry_high": 0.0, "tp1": 0.0, "tp2": 0.0, "tp3": 0.0, "sl": 0.0, "reasons": [], "tf_bias": "NEUTRAL"}

        class Session:
            last_fetch_time = None
            last_price_bid = None
            last_price_ask = None
            last_price_high = None
            last_price_low = None

        with patch.object(api.database, "get_or_create_session", return_value=Session()), patch.object(api, "fetch_xauusd_price", new=AsyncMock(return_value={"bid": 3055.5, "ask": 3055.9, "high": 3060, "low": 3040})), patch.object(api, "get_smc_signal", new=fake_signal), patch.object(api.database, "update_session"):
            result = asyncio.run(api.get_cached_or_fresh_price(12345))
        self.assertEqual(result["bid"], 3055.5)
        self.assertEqual(captured["price"], 3055.5)

    def test_telegram_webhook_requires_secret_even_when_unconfigured(self):
        app_module = importlib.import_module("app")
        app_module.TELEGRAM_WEBHOOK_SECRET = "expected-secret"
        app_module.telegram_app = None
        request = type("Request", (), {})()
        request.json = AsyncMock(return_value={})
        with self.assertRaises(Exception) as ctx:
            asyncio.run(app_module.telegram_webhook(request, None))
        self.assertIn("403", str(ctx.exception))

    def test_notification_sweep_query_exists(self):
        storage = importlib.import_module("whop_storage")
        self.assertTrue(callable(storage.list_unnotified_orders))

    def test_cache_contract_is_ten_seconds(self):
        api = importlib.import_module("api_handler")
        self.assertEqual(api.SESSION_CACHE_TTL, 10)
        self.assertEqual(api.CANDLE_CACHE_TTL, 10)


if __name__ == "__main__":
    unittest.main()
