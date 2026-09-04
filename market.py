from __future__ import annotations
import logging
from datetime import datetime, timezone
import asyncio
import aiohttp
import database
from config import GOLDAPI_API_KEY, MARKET_POLL_SECONDS

log = logging.getLogger('market')
URL = 'https://www.goldapi.io/api/XAU/USD'

async def fetch_spot() -> dict:
    headers = {'x-access-token': GOLDAPI_API_KEY, 'Content-Type': 'application/json'}
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.get(URL, headers=headers) as r:
            r.raise_for_status(); data = await r.json()
    return {'price': float(data['price']), 'change_pct': float(data.get('chp') or 0), 'ts': datetime.now(timezone.utc)}

async def poll_once() -> dict:
    tick = await fetch_spot(); database.save_sample(tick['price'], tick['change_pct'], tick['ts']); return tick

async def run_poller(stop_event) -> None:
    while not stop_event.is_set():
        try: await poll_once()
        except Exception: log.exception('market poll failed')
        try: await asyncio.wait_for(stop_event.wait(), timeout=MARKET_POLL_SECONDS)
        except TimeoutError: pass
