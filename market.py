from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import aiohttp

import database
from config import GOLDAPI_API_KEY, MARKET_POLL_SECONDS

log = logging.getLogger('market')
URL = 'https://www.goldapi.io/api/price/XAU/USD'
MIN_PRICE = 1000.0
MAX_PRICE = 10000.0
REQUEST_TIMEOUT_SECONDS = 15
MAX_BACKOFF_SECONDS = max(300, MARKET_POLL_SECONDS * 5)


def validate_price(price: float) -> float:
    if not MIN_PRICE <= price <= MAX_PRICE:
        raise ValueError('goldapi_price_out_of_range')
    return price


async def fetch_spot(session: aiohttp.ClientSession) -> dict:
    headers = {'x-access-token': GOLDAPI_API_KEY, 'Content-Type': 'application/json'}
    async with session.get(URL, headers=headers) as response:
        response.raise_for_status()
        data = await response.json()
    price = validate_price(float(data['price']))
    return {'price': price, 'change_pct': float(data.get('chp') or 0), 'ts': datetime.now(timezone.utc)}


async def poll_once(session: aiohttp.ClientSession | None = None) -> dict:
    owned = session is None
    if owned:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        session = aiohttp.ClientSession(timeout=timeout)
    try:
        tick = await fetch_spot(session)
        # SQLAlchemy is synchronous; never run it on the asyncio event loop.
        await asyncio.to_thread(database.save_sample, tick['price'], tick['change_pct'], tick['ts'])
        return tick
    finally:
        if owned:
            await session.close()


async def run_poller(stop_event) -> None:
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
    backoff = max(1, MARKET_POLL_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while not stop_event.is_set():
            try:
                await poll_once(session)
                backoff = max(1, MARKET_POLL_SECONDS)
            except Exception:
                log.exception('market poll failed')
                backoff = min(max(MARKET_POLL_SECONDS, backoff * 2), MAX_BACKOFF_SECONDS)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=backoff)
            except TimeoutError:
                pass
