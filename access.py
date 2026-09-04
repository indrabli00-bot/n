from __future__ import annotations
import time
import logging
from telegram import Bot
from config import TELEGRAM_PREMIUM_CHAT_ID
from database import membership_active

log = logging.getLogger('access')
_cache: dict[int, tuple[float, bool]] = {}
TTL = 60

async def channel_member(bot: Bot, telegram_id: int) -> bool:
    cached = _cache.get(telegram_id)
    if cached and cached[0] > time.monotonic(): return cached[1]
    try:
        member = await bot.get_chat_member(TELEGRAM_PREMIUM_CHAT_ID, telegram_id)
        ok = member.status in {'member', 'administrator', 'creator'}
    except Exception as exc:
        log.warning('membership check failed: %s', type(exc).__name__); ok = False
    _cache[telegram_id] = (time.monotonic() + TTL, ok)
    return ok

async def has_access(bot: Bot, telegram_id: int) -> bool:
    if not membership_active(telegram_id): return False
    return await channel_member(bot, telegram_id)
