"""NEURAL GOLD v3.2 checkout-link adapter.

Customer navigation is owned by ``ui_contract.py``. This module intentionally
contains only the checkout URL contract used by the canonical access screen.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import quote

from config import BELMO_PUBLIC_URL, TELEGRAM_BOT_TOKEN


def checkout_link(telegram_id: int, days: int) -> str:
    if days not in (7, 14, 30):
        raise ValueError("Unsupported subscription duration")
    if not BELMO_PUBLIC_URL:
        raise RuntimeError("BELMO_PUBLIC_URL is required for checkout links")
    expires = int(time.time()) + 15 * 60
    payload = f"{telegram_id}:{days}:{expires}"
    key = TELEGRAM_BOT_TOKEN.encode("utf-8")
    signature = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{BELMO_PUBLIC_URL}/checkout/{days}?token={quote(payload + '.' + signature)}"
