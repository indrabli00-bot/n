from __future__ import annotations

import asyncio
import hashlib
import json
import logging

import database
import signal_engine

log = logging.getLogger('publisher')
_last_published_fingerprint: str | None = None


def fingerprint(candidate: dict) -> str:
    return hashlib.sha256(json.dumps({'signal': candidate.get('signal')}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def should_publish(candidate: dict) -> bool:
    direction = candidate.get('signal')
    if direction == 'HOLD':
        return False
    if direction not in {'LONG', 'SHORT'}:
        return False
    return fingerprint(candidate) != _last_published_fingerprint


def mark_published(candidate: dict) -> None:
    global _last_published_fingerprint
    _last_published_fingerprint = fingerprint(candidate)


async def evaluate_and_publish(bot, chat_id: int, formatter) -> dict:
    samples = await asyncio.to_thread(database.recent_samples)
    candidate = signal_engine.analyze(samples)
    if not should_publish(candidate):
        return {'candidate': candidate, 'published': False}
    try:
        await bot.send_message(chat_id, '<b>📡 NEURAL STRIKES</b>\n\n' + formatter(candidate), parse_mode='HTML')
        mark_published(candidate)
        return {'candidate': candidate, 'published': True}
    except Exception:
        log.exception('automatic signal channel publication failed; will retry on next market tick')
        return {'candidate': candidate, 'published': False}
