from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import inspect, text

import database
import signal_engine

log = logging.getLogger('publisher')
STATE_TABLE = 'signal_publication_state'
PUBLISH_LEASE_SECONDS = 120
_publish_lock = asyncio.Lock()


def init_state() -> None:
    with database.engine.begin() as conn:
        conn.execute(
            text(
                f'CREATE TABLE IF NOT EXISTS {STATE_TABLE} '
                '(id INTEGER PRIMARY KEY, last_direction VARCHAR(20), '
                'updated_at TIMESTAMP, claim_direction VARCHAR(20), '
                'claim_token VARCHAR(64), claimed_at TIMESTAMP)'
            )
        )
        # Inspect through the same connection/transaction. Inspecting the engine
        # here would open a second connection and, on PostgreSQL, cannot see the
        # CREATE TABLE until this transaction commits.
        columns = {column['name'] for column in inspect(conn).get_columns(STATE_TABLE)}
        migrations = {
            'claim_direction': 'VARCHAR(20)',
            'claim_token': 'VARCHAR(64)',
            'claimed_at': 'TIMESTAMP',
        }
        for column, definition in migrations.items():
            if column not in columns:
                conn.execute(text(f'ALTER TABLE {STATE_TABLE} ADD COLUMN {column} {definition}'))
        conn.execute(
            text(
                f'INSERT INTO {STATE_TABLE} '
                '(id, last_direction, updated_at, claim_direction, claim_token, claimed_at) '
                'VALUES (1, NULL, NULL, NULL, NULL, NULL) '
                'ON CONFLICT (id) DO NOTHING'
            )
        )


def _claim_publication(direction: str) -> str | None:
    token = uuid.uuid4().hex
    cutoff = datetime.now(timezone.utc).timestamp() - PUBLISH_LEASE_SECONDS
    with database.engine.begin() as conn:
        result = conn.execute(
            text(
                f'UPDATE {STATE_TABLE} SET claim_direction = :direction, '
                'claim_token = :token, claimed_at = CURRENT_TIMESTAMP '
                'WHERE id = 1 '
                'AND (last_direction IS NULL OR last_direction != :direction) '
                'AND (claim_token IS NULL OR claimed_at IS NULL OR claimed_at < :cutoff)'
            ),
            {
                'direction': direction,
                'token': token,
                'cutoff': datetime.fromtimestamp(cutoff, timezone.utc),
            },
        )
    return token if result.rowcount == 1 else None


def _release_publication(token: str) -> None:
    with database.engine.begin() as conn:
        conn.execute(
            text(
                f'UPDATE {STATE_TABLE} SET claim_direction = NULL, '
                'claim_token = NULL, claimed_at = NULL '
                'WHERE id = 1 AND claim_token = :token'
            ),
            {'token': token},
        )


def _complete_publication(direction: str, token: str) -> None:
    with database.engine.begin() as conn:
        result = conn.execute(
            text(
                f'UPDATE {STATE_TABLE} SET last_direction = :direction, '
                'updated_at = CURRENT_TIMESTAMP, claim_direction = NULL, '
                'claim_token = NULL, claimed_at = NULL '
                'WHERE id = 1 AND claim_token = :token AND claim_direction = :direction'
            ),
            {'direction': direction, 'token': token},
        )
    if result.rowcount != 1:
        raise RuntimeError('publication_claim_lost')


async def evaluate_and_publish(bot, chat_id: int, formatter) -> dict:
    async with _publish_lock:
        samples = await asyncio.to_thread(database.recent_samples)
        candidate = signal_engine.analyze(samples)
        direction = candidate.get('signal')
        if direction not in {'LONG', 'SHORT'}:
            return {'candidate': candidate, 'published': False}

        claim_token = await asyncio.to_thread(_claim_publication, direction)
        if claim_token is None:
            return {'candidate': candidate, 'published': False, 'claimed': False}

        try:
            await bot.send_message(
                chat_id,
                '<b>📡 NEURAL STRIKES</b>\n\n' + formatter(candidate),
                parse_mode='HTML',
            )
        except Exception:
            await asyncio.to_thread(_release_publication, claim_token)
            log.exception('automatic signal channel publication failed')
            return {'candidate': candidate, 'published': False, 'claimed': True}

        try:
            await asyncio.to_thread(_complete_publication, direction, claim_token)
        except Exception:
            log.exception(
                'signal delivered to Telegram but publication claim completion failed; '
                'lease will expire before another worker can reclaim it'
            )
            return {
                'candidate': candidate,
                'published': True,
                'state_persisted': False,
            }

        return {
            'candidate': candidate,
            'published': True,
            'state_persisted': True,
        }
