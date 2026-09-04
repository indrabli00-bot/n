from __future__ import annotations

import asyncio
import hashlib
import json
import logging

import database
import signal_engine
from sqlalchemy import text

log = logging.getLogger('publisher')
STATE_TABLE = 'signal_publication_state'


def init_state() -> None:
    with database.engine.begin() as conn:
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS {STATE_TABLE} (id INTEGER PRIMARY KEY, last_direction VARCHAR(20), updated_at TIMESTAMP)'))


def fingerprint(candidate: dict) -> str:
    return hashlib.sha256(json.dumps({'signal': candidate.get('signal')}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def last_published_fingerprint() -> str | None:
    with database.engine.connect() as conn:
        row = conn.execute(text(f'SELECT last_direction FROM {STATE_TABLE} WHERE id = 1')).first()
    if not row or not row[0]:
        return None
    return fingerprint({'signal': row[0]})


def should_publish(candidate: dict) -> bool:
    direction = candidate.get('signal')
    if direction not in {'LONG', 'SHORT'}:
        return False
    return fingerprint(candidate) != last_published_fingerprint()


def mark_published(candidate: dict) -> None:
    direction = candidate['signal']
    with database.engine.begin() as conn:
        conn.execute(text(f'DELETE FROM {STATE_TABLE} WHERE id = 1'))
        conn.execute(text(f'INSERT INTO {STATE_TABLE} (id, last_direction, updated_at) VALUES (1, :direction, CURRENT_TIMESTAMP)'), {'direction': direction})


async def evaluate_and_publish(bot, chat_id: int, formatter) -> dict:
    samples = await asyncio.to_thread(database.recent_samples)
    candidate = signal_engine.analyze(samples)
    if not should_publish(candidate):
        return {'candidate': candidate, 'published': False}
    try:
        await bot.send_message(chat_id, '<b>📡 NEURAL STRIKES</b>\n\n' + formatter(candidate), parse_mode='HTML')
        await asyncio.to_thread(mark_published, candidate)
        return {'candidate': candidate, 'published': True}
    except Exception:
        log.exception('automatic signal channel publication failed; will retry on next market tick')
        return {'candidate': candidate, 'published': False}
