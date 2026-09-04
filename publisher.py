from __future__ import annotations

import asyncio
import hashlib
import json
import logging

from sqlalchemy import text

import database
import signal_engine

log = logging.getLogger('publisher')
STATE_TABLE = 'signal_publication_state'
MARK_RETRIES = 3
MARK_RETRY_DELAY_SECONDS = 0.5
_publish_lock = asyncio.Lock()

# If Telegram confirms delivery but the DB is temporarily unavailable, keep the
# most recently delivered fingerprint suppressed for this process so the next
# market tick cannot send the same signal again. A process restart still
# requires persistent recovery.
_recently_sent: set[str] = set()


def init_state() -> None:
    with database.engine.begin() as conn:
        conn.execute(
            text(
                f'CREATE TABLE IF NOT EXISTS {STATE_TABLE} '
                '(id INTEGER PRIMARY KEY, last_direction VARCHAR(20), '
                'updated_at TIMESTAMP)'
            )
        )


def fingerprint(candidate: dict) -> str:
    payload = {'signal': candidate.get('signal')}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
    ).hexdigest()


def last_published_fingerprint() -> str | None:
    with database.engine.connect() as conn:
        row = conn.execute(
            text(f'SELECT last_direction FROM {STATE_TABLE} WHERE id = 1')
        ).first()
    if not row or not row[0]:
        return None
    return fingerprint({'signal': row[0]})


def should_publish(candidate: dict) -> bool:
    direction = candidate.get('signal')
    if direction not in {'LONG', 'SHORT'}:
        return False
    signal_fingerprint = fingerprint(candidate)
    if signal_fingerprint in _recently_sent:
        return False
    return signal_fingerprint != last_published_fingerprint()


def mark_published(candidate: dict) -> None:
    direction = candidate['signal']
    with database.engine.begin() as conn:
        conn.execute(text(f'DELETE FROM {STATE_TABLE} WHERE id = 1'))
        conn.execute(
            text(
                f'INSERT INTO {STATE_TABLE} '
                '(id, last_direction, updated_at) '
                'VALUES (1, :direction, CURRENT_TIMESTAMP)'
            ),
            {'direction': direction},
        )


async def _mark_published_with_retry(candidate: dict) -> bool:
    for attempt in range(1, MARK_RETRIES + 1):
        try:
            await asyncio.to_thread(mark_published, candidate)
            return True
        except Exception:
            if attempt == MARK_RETRIES:
                log.exception(
                    'publication state persistence failed after %s attempts',
                    MARK_RETRIES,
                )
                return False
            log.warning(
                'publication state persistence failed; retrying (%s/%s)',
                attempt,
                MARK_RETRIES,
                exc_info=True,
            )
            await asyncio.sleep(MARK_RETRY_DELAY_SECONDS)
    return False


async def evaluate_and_publish(bot, chat_id: int, formatter) -> dict:
    async with _publish_lock:
        samples = await asyncio.to_thread(database.recent_samples)
        candidate = signal_engine.analyze(samples)
        if not should_publish(candidate):
            return {'candidate': candidate, 'published': False}

        try:
            await bot.send_message(
                chat_id,
                '<b>📡 NEURAL STRIKES</b>\n\n' + formatter(candidate),
                parse_mode='HTML',
            )
        except Exception:
            log.exception('automatic signal channel publication failed')
            return {'candidate': candidate, 'published': False}

        signal_fingerprint = fingerprint(candidate)
        _recently_sent.clear()
        _recently_sent.add(signal_fingerprint)
        persisted = await _mark_published_with_retry(candidate)
        if not persisted:
            log.error(
                'signal delivered to Telegram but publication state is not persisted; '
                'suppressing duplicate for the current process'
            )
            return {
                'candidate': candidate,
                'published': True,
                'state_persisted': False,
            }

        _recently_sent.discard(signal_fingerprint)
        return {
            'candidate': candidate,
            'published': True,
            'state_persisted': True,
        }
