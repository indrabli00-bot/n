"""NEURAL GOLD v3.2 checkout-link adapter.

Customer-facing Telegram navigation is owned exclusively by ``main.py``.
This module only provides the checkout URL contract used by the access screen.
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
    base_url = BELMO_PUBLIC_URL or "http://localhost"
    expires = int(time.time()) + 15 * 60
    payload = f"{telegram_id}:{days}:{expires}"
    key = TELEGRAM_BOT_TOKEN.encode("utf-8")
    signature = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{base_url}/checkout/{days}?token={quote(payload + '.' + signature)}"
