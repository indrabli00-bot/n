from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import aiohttp

import database
from config import (
    WHOP_OAUTH_CLIENT_ID,
    WHOP_OAUTH_CLIENT_SECRET,
    WHOP_OAUTH_REDIRECT_URI,
    WHOP_OAUTH_STATE_SECRET,
    WHOP_WEBHOOK_SECRET,
)

OAUTH_BASE = 'https://api.whop.com/oauth'


def verify_webhook(payload: bytes, headers) -> dict:
    normalized = {str(k).lower(): str(v) for k, v in headers.items()}
    webhook_id = normalized.get('webhook-id', '')
    timestamp = normalized.get('webhook-timestamp', '')
    signature = normalized.get('webhook-signature', '')

    if not webhook_id or not timestamp or not signature:
        raise ValueError('missing_webhook_headers')
    if abs(time.time() - int(timestamp)) > 300:
        raise ValueError('webhook_timestamp_expired')

    secret = WHOP_WEBHOOK_SECRET
    key = secret[6:] if secret.startswith('whsec_') else secret
    try:
        key = base64.b64decode(key + '=' * ((4 - len(key) % 4) % 4))
    except Exception:
        key = key.encode()

    signed = f'{webhook_id}.{timestamp}.'.encode() + payload
    digest = base64.b64encode(
        hmac.new(key, signed, hashlib.sha256).digest()
    ).decode()
    valid = any(
        item.startswith('v1,')
        and hmac.compare_digest(item[3:], digest)
        for item in signature.split()
    )
    if not valid:
        raise ValueError('invalid_webhook_signature')

    data = json.loads(payload)
    data['_webhook_id'] = webhook_id
    return data


def _pkce_verifier() -> str:
    return secrets.token_urlsafe(48)


def _pkce_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b'=').decode()


def _signed_state(telegram_id: int, nonce: str) -> str:
    body = f'{telegram_id}:{nonce}:{int(time.time())}'
    signature = hmac.new(
        WHOP_OAUTH_STATE_SECRET.encode(),
        body.encode(),
        hashlib.sha256,
    ).hexdigest()
    return base64.urlsafe_b64encode(
        f'{body}:{signature}'.encode()
    ).rstrip(b'=').decode()


def _valid_state(state: str, telegram_id: int) -> bool:
    try:
        raw = base64.urlsafe_b64decode(
            state + '=' * ((4 - len(state) % 4) % 4)
        ).decode()
        user_id, nonce, issued, signature = raw.split(':', 3)
        body = f'{user_id}:{nonce}:{issued}'
        expected = hmac.new(
            WHOP_OAUTH_STATE_SECRET.encode(),
            body.encode(),
            hashlib.sha256,
        ).hexdigest()
        return (
            int(user_id) == telegram_id
            and abs(time.time() - int(issued)) <= 600
            and hmac.compare_digest(signature, expected)
        )
    except Exception:
        return False


async def create_link_url(telegram_id: int) -> str:
    verifier = _pkce_verifier()
    nonce = secrets.token_urlsafe(18)
    state = _signed_state(telegram_id, nonce)
    database.save_oauth_state(
        state,
        telegram_id,
        verifier,
        datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    params = {
        'client_id': WHOP_OAUTH_CLIENT_ID,
        'redirect_uri': WHOP_OAUTH_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'openid profile',
        'state': state,
        'nonce': nonce,
        'code_challenge': _pkce_challenge(verifier),
        'code_challenge_method': 'S256',
    }
    return f'{OAUTH_BASE}/authorize?{urlencode(params)}'


async def exchange_code(code: str, state: str) -> tuple[int, str]:
    row = database.consume_oauth_state(state)
    if not row:
        raise ValueError('oauth_state_invalid_or_expired')
    if not _valid_state(state, row.telegram_id):
        raise ValueError('oauth_state_invalid')

    payload = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': WHOP_OAUTH_REDIRECT_URI,
        'client_id': WHOP_OAUTH_CLIENT_ID,
        'client_secret': WHOP_OAUTH_CLIENT_SECRET,
        'code_verifier': row.code_verifier,
    }
    timeout = aiohttp.ClientTimeout(total=15)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            f'{OAUTH_BASE}/token',
            data=payload,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        ) as response:
            token = await response.json(content_type=None)
            if response.status >= 300:
                raise RuntimeError(f'whop_oauth_token_{response.status}')

        access_token = str(token.get('access_token') or '')
        if not access_token:
            raise RuntimeError('whop_oauth_missing_access_token')

        async with session.get(
            f'{OAUTH_BASE}/userinfo',
            headers={'Authorization': f'Bearer {access_token}'},
        ) as response:
            userinfo = await response.json(content_type=None)
            if response.status >= 300:
                raise RuntimeError(f'whop_oauth_userinfo_{response.status}')

    whop_user_id = str(userinfo.get('sub') or '')
    if not whop_user_id:
        raise RuntimeError('whop_oauth_missing_user_id')
    return row.telegram_id, whop_user_id
