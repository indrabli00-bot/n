from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
import aiohttp
import database
from config import GOLDAPI_API_KEY, MARKET_POLL_SECONDS

log = logging.getLogger('market')
URL = 'https://www.goldapi.io/api/XAU/USD'
MAX_BACKOFF_SECONDS = max(300, MARKET_POLL_SECONDS * 5)

async def fetch_spot(session: aiohttp.ClientSession) -> dict:
    headers = {'x-access-token': GOLDAPI_API_KEY, 'Content-Type': 'application/json'}
    async with session.get(URL, headers=headers) as r:
        r.raise_for_status()
        data = await r.json()
    price = float(data['price'])
    if not 1000 <= price <= 10000:
        raise ValueError('goldapi_price_out_of_range')
    return {'price': price, 'change_pct': float(data.get('chp') or 0), 'ts': datetime.now(timezone.utc)}

async def poll_once(session: aiohttp.ClientSession | None = None) -> dict:
    if session is not None:
        tick = await fetch_spot(session)
    else:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as owned:
            tick = await fetch_spot(owned)
    database.save_sample(tick['price'], tick['change_pct'], tick['ts'])
    return tick

async def run_poller(stop_event) -> None:
    timeout = aiohttp.ClientTimeout(total=15)
    backoff = MARKET_POLL_SECONDS
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while not stop_event.is_set():
            try:
                await poll_once(session)
                backoff = MARKET_POLL_SECONDS
            except Exception:
                log.exception('market poll failed')
                backoff = min(max(MARKET_POLL_SECONDS, backoff * 2), MAX_BACKOFF_SECONDS)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=backoff)
            except TimeoutError:
                pass
