from __future__ import annotations

import logging
import time
from collections import OrderedDict

from telegram import Bot
from config import TELEGRAM_PREMIUM_CHAT_ID

log = logging.getLogger('access')
TTL = 10
MAX_CACHE_ENTRIES = 2048
_cache: OrderedDict[int, tuple[float, bool]] = OrderedDict()


def _member_is_active(member) -> bool:
    """Normalize Telegram member states, including restricted members."""
    status = getattr(member, 'status', '')
    if status in {'member', 'administrator', 'creator'}:
        return True
    return status == 'restricted' and bool(getattr(member, 'is_member', False))


def _prune_cache(now: float) -> None:
    while _cache:
        telegram_id, (expires_at, _) = next(iter(_cache.items()))
        if expires_at > now:
            break
        _cache.pop(telegram_id, None)

    while len(_cache) > MAX_CACHE_ENTRIES:
        _cache.popitem(last=False)


async def channel_member(bot: Bot, telegram_id: int) -> bool:
    now = time.monotonic()
    cached = _cache.get(telegram_id)
    if cached and cached[0] > now:
        _cache.move_to_end(telegram_id)
        return cached[1]
    if cached:
        _cache.pop(telegram_id, None)

    try:
        member = await bot.get_chat_member(TELEGRAM_PREMIUM_CHAT_ID, telegram_id)
        ok = _member_is_active(member)
    except Exception as exc:
        log.warning('premium channel membership check failed: %s', type(exc).__name__)
        ok = False

    _cache[telegram_id] = (time.monotonic() + TTL, ok)
    _cache.move_to_end(telegram_id)
    _prune_cache(time.monotonic())
    return ok


async def has_access(bot: Bot, telegram_id: int) -> bool:
    """Check bonus-bot access from Premium Channel membership.

    Whop controls the purchased entitlement and Premium Channel access.
    The Telegram bot is only a bonus utility for members who already have
    channel access, so OAuth/Whop account linking is not part of bot access.
    """
    return await channel_member(bot, telegram_id)
