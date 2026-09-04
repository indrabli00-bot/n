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
    stable = {k: candidate.get(k) for k in ('signal', 'entry', 'tp', 'stop', 'reason', 'timeframe')}
    return hashlib.sha256(json.dumps(stable, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def should_publish(candidate: dict) -> bool:
    global _last_published_fingerprint
    if candidate.get('signal') not in {'LONG', 'SHORT'}:
        return False
    fp = fingerprint(candidate)
    if fp == _last_published_fingerprint:
        return False
    _last_published_fingerprint = fp
    return True


async def evaluate_and_publish(bot, chat_id: int, formatter) -> dict:
    samples = await asyncio.to_thread(database.recent_samples)
    candidate = signal_engine.analyze(samples)
    if not should_publish(candidate):
        return {'candidate': candidate, 'published': False}
    try:
        await bot.send_message(chat_id, '<b>📡 NEURAL STRIKES</b>\n\n' + formatter(candidate), parse_mode='HTML')
        return {'candidate': candidate, 'published': True}
    except Exception:
        log.exception('automatic signal channel publication failed')
        return {'candidate': candidate, 'published': False}
