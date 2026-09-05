from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timezone

import aiohttp

import database
from config import MARKET_POLL_SECONDS

log = logging.getLogger('market')
URL = 'https://api.gold-api.com/price/XAU/USD'
MIN_PRICE = 1000.0
MAX_PRICE = 10000.0
REQUEST_TIMEOUT_SECONDS = 15
MAX_BACKOFF_SECONDS = max(300, MARKET_POLL_SECONDS * 5)
CACHE_SECONDS = 30


def _finite_float(value: object, error: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(error) from exc
    if not math.isfinite(number):
        raise ValueError(error)
    return number


def validate_price(price: float) -> float:
    if not math.isfinite(price) or not MIN_PRICE <= price <= MAX_PRICE:
        raise ValueError('goldapi_price_out_of_range')
    return price


def _response_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    except ValueError:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


async def fetch_spot(session: aiohttp.ClientSession) -> dict:
    # Real-time prices are public and explicitly do not require an API key.
    # The upstream service asks clients to cache responses for 30 seconds.
    headers = {'Accept': 'application/json'}
    async with session.get(
        URL,
        headers=headers,
        params=None,
    ) as response:
        response.raise_for_status()
        data = await response.json()

    if not isinstance(data, dict):
        raise ValueError('goldapi_response_invalid')

    price = validate_price(_finite_float(data.get('price'), 'goldapi_price_invalid'))
    # The new API does not expose the legacy `chp` field. Preserve a safe
    # default because the signal engine does not depend on this value.
    change_pct = _finite_float(data.get('chp') or 0, 'goldapi_change_pct_invalid')
    return {
        'price': price,
        'change_pct': change_pct,
        'ts': _response_timestamp(data.get('updatedAt')),
    }


async def poll_once(session: aiohttp.ClientSession | None = None) -> dict:
    owned = session is None
    if owned:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        session = aiohttp.ClientSession(timeout=timeout)

    try:
        tick = await fetch_spot(session)
        await asyncio.to_thread(
            database.save_sample,
            tick['price'],
            tick['change_pct'],
            tick['ts'],
        )
        return tick
    finally:
        if owned and session is not None:
            await session.close()


async def run_poller(stop_event, on_tick=None) -> None:
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
    backoff = max(CACHE_SECONDS, MARKET_POLL_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while not stop_event.is_set():
            try:
                await poll_once(session)
                backoff = max(CACHE_SECONDS, MARKET_POLL_SECONDS)
                if on_tick is not None:
                    try:
                        await on_tick()
                    except Exception:
                        log.exception('automatic signal evaluation failed')
            except Exception:
                log.exception('market poll failed')
                backoff = min(
                    max(CACHE_SECONDS, backoff * 2),
                    MAX_BACKOFF_SECONDS,
                )

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=backoff)
            except TimeoutError:
                pass
