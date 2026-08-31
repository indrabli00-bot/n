"""Phase 0.2 tests: multi-source price cascade + circuit breaker + stale cache jujur."""
import asyncio
import io
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:TEST")
os.environ.setdefault("GOLDAPI_API_KEY", "test-key")

import price_sources as ps


def _px(price=2350.0, source="X"):
    return {"source": source, "symbol": "XAU/USD", "bid": price, "ask": price, "close": price,
            "high": price, "low": price, "change": 0.0, "change_percent": 0.0, "volume": "N/A",
            "timestamp": datetime.now(timezone.utc).isoformat()}


class PriceCascadeTests(unittest.TestCase):
    def setUp(self):
        ps._breaker.clear()
        ps._last_good = None
        ps._last_good_ts = None
        self.attempts = []
        self._orig_sources = ps._SOURCES[:]

    def tearDown(self):
        ps._SOURCES[:] = self._orig_sources
        ps._breaker.clear()
        ps._last_good = None
        ps._last_good_ts = None

    def _set_sources(self, *pairs):
        ps._SOURCES[:] = list(pairs)

    def _ok(self, source):
        async def fetch():
            self.attempts.append(source)
            return _px(2350.0, source)
        return fetch

    def _bad(self, source):
        async def fetch():
            self.attempts.append(source)
            raise ps.SourceUnavailable(f"{source} down")
        return fetch

    # 1. primary sehat -> tanpa fallback
    def test_primary_healthy_no_fallback(self):
        self._set_sources(("PRIMARY", self._ok("PRIMARY")), ("SECONDARY", self._bad("SECONDARY")))
        out = asyncio.run(ps.fetch_price_cascade())
        self.assertEqual(out["source"], "PRIMARY")
        self.assertEqual(self.attempts, ["PRIMARY"])
        self.assertNotIn("stale", out)

    # 2. primary gagal -> secondary dipakai
    def test_primary_fails_secondary_used(self):
        self._set_sources(("PRIMARY", self._bad("PRIMARY")), ("SECONDARY", self._ok("SECONDARY")))
        out = asyncio.run(ps.fetch_price_cascade())
        self.assertEqual(out["source"], "SECONDARY")
        self.assertEqual(self.attempts, ["PRIMARY", "SECONDARY"])

    # 3. semua gagal + tanpa cache -> LIVE FEED UNAVAILABLE
    def test_all_fail_no_cache_raises(self):
        self._set_sources(("PRIMARY", self._bad("PRIMARY")), ("SECONDARY", self._bad("SECONDARY")))
        with self.assertRaises(RuntimeError):
            asyncio.run(ps.fetch_price_cascade())

    # 4. semua gagal + cache valid -> STALE jujur
    def test_all_fail_stale_cache_served(self):
        ps._remember_last_good(_px(2340.0, "PRIMARY"))
        self._set_sources(("PRIMARY", self._bad("PRIMARY")))
        out = asyncio.run(ps.fetch_price_cascade())
        self.assertTrue(out.get("stale"))
        self.assertIn("STALE", out["source"])
        self.assertEqual(out["close"], 2340.0)

    # 5. cache terlalu tua -> tetap raise (tanpa fabrikasi)
    def test_stale_cache_expired_raises(self):
        ps._last_good = _px(2340.0, "PRIMARY")
        ps._last_good_ts = datetime.now(timezone.utc) - timedelta(minutes=45)
        self._set_sources(("PRIMARY", self._bad("PRIMARY")))
        with self.assertRaises(RuntimeError):
            asyncio.run(ps.fetch_price_cascade())

    # 6. circuit breaker: 3 gagal beruntun -> primary di-skip selama cooldown
    def test_circuit_breaker_opens_after_3_failures(self):
        self._set_sources(("PRIMARY", self._bad("PRIMARY")), ("SECONDARY", self._ok("SECONDARY")))
        for _ in range(3):
            asyncio.run(ps.fetch_price_cascade())
        self.assertEqual(self.attempts.count("PRIMARY"), 3)
        self.attempts.clear()
        asyncio.run(ps.fetch_price_cascade())
        self.assertNotIn("PRIMARY", self.attempts)
        self.assertIn("SECONDARY", self.attempts)

    # 7. cooldown habis -> primary dicoba lagi
    def test_circuit_breaker_cooldown_expiry_retries_primary(self):
        self._set_sources(("PRIMARY", self._bad("PRIMARY")), ("SECONDARY", self._ok("SECONDARY")))
        for _ in range(3):
            asyncio.run(ps.fetch_price_cascade())
        ps._breaker["PRIMARY"]["cooldown_until"] = 0.0
        self.attempts.clear()
        asyncio.run(ps.fetch_price_cascade())
        self.assertIn("PRIMARY", self.attempts)

    # 8. sumber keyless: bid = ask = mid (tanpa spread rekaan) — asersi struktural
    def test_keyless_source_honest_bid_ask(self):
        src_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "price_sources.py")
        src = io.open(src_path, encoding="utf-8").read()
        seg = src.split("async def fetch_goldapi_com")[1].split("async def fetch_goldprice_org")[0]
        self.assertIn('"bid": price', seg)
        self.assertIn('"ask": price', seg)
        self.assertIn("tanpa spread rekaan", seg)


if __name__ == "__main__":
    unittest.main()
