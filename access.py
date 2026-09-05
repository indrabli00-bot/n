from __future__ import annotations

import logging
import time

from telegram import Bot
from config import TELEGRAM_PREMIUM_CHAT_ID

log = logging.getLogger('access')
_cache: dict[int, tuple[float, bool]] = {}
TTL = 10


def _member_is_active(member) -> bool:
    """Normalize Telegram member states, including restricted members."""
    status = getattr(member, 'status', '')
    if status in {'member', 'administrator', 'creator'}:
        return True
    return status == 'restricted' and bool(getattr(member, 'is_member', False))


async def channel_member(bot: Bot, telegram_id: int) -> bool:
    cached = _cache.get(telegram_id)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    try:
        member = await bot.get_chat_member(TELEGRAM_PREMIUM_CHAT_ID, telegram_id)
        ok = _member_is_active(member)
    except Exception as exc:
        log.warning('premium channel membership check failed: %s', type(exc).__name__)
        ok = False
    _cache[telegram_id] = (time.monotonic() + TTL, ok)
    return ok


async def has_access(bot: Bot, telegram_id: int) -> bool:
    """Check bonus-bot access from Premium Channel membership.

    Whop controls the purchased entitlement and Premium Channel access.
    The Telegram bot is only a bonus utility for members who already have
    channel access, so OAuth/Whop account linking is not part of bot access.
    """
    return await channel_member(bot, telegram_id)
