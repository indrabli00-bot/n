from __future__ import annotations
import base64, hashlib, hmac, json, secrets, time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
import aiohttp
import database
from config import (
    WHOP_OAUTH_CLIENT_ID,
    WHOP_OAUTH_CLIENT_SECRET, WHOP_OAUTH_REDIRECT_URI,
    WHOP_OAUTH_STATE_SECRET, WHOP_PRODUCT_URL, WHOP_WEBHOOK_SECRET,
)

OAUTH_BASE = 'https://api.whop.com/oauth'

def verify_webhook(payload: bytes, headers) -> dict:
    h = {str(k).lower(): str(v) for k, v in headers.items()}
    wid, ts, sig = h.get('webhook-id', ''), h.get('webhook-timestamp', ''), h.get('webhook-signature', '')
    if not wid or not ts or not sig: raise ValueError('missing_webhook_headers')
    if abs(time.time() - int(ts)) > 300: raise ValueError('webhook_timestamp_expired')
    secret = WHOP_WEBHOOK_SECRET
    key = secret[6:] if secret.startswith('whsec_') else secret
    try: key = base64.b64decode(key + '=' * ((4 - len(key) % 4) % 4))
    except Exception: key = key.encode()
    signed = f'{wid}.{ts}.'.encode() + payload
    digest = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    if not any(x.startswith('v1,') and hmac.compare_digest(x[3:], digest) for x in sig.split()): raise ValueError('invalid_webhook_signature')
    data = json.loads(payload)
    data['_webhook_id'] = wid
    return data

def _pkce_verifier() -> str:
    return secrets.token_urlsafe(48)

def _pkce_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()

def _signed_state(telegram_id: int, nonce: str) -> str:
    body = f'{telegram_id}:{nonce}:{int(time.time())}'
    sig = hmac.new(WHOP_OAUTH_STATE_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f'{body}:{sig}'.encode()).decode().rstrip('=')

def _valid_state(state: str, telegram_id: int) -> bool:
    try:
        raw = base64.urlsafe_b64decode(state + '=' * ((4 - len(state) % 4) % 4)).decode()
        uid, nonce, issued, sig = raw.split(':', 3)
        body = f'{uid}:{nonce}:{issued}'
        expected = hmac.new(WHOP_OAUTH_STATE_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
        return int(uid) == telegram_id and abs(time.time() - int(issued)) <= 600 and hmac.compare_digest(sig, expected)
    except Exception:
        return False

async def create_link_url(telegram_id: int) -> str:
    verifier = _pkce_verifier()
    state = _signed_state(telegram_id, secrets.token_urlsafe(18))
    database.save_oauth_state(state, telegram_id, verifier, datetime.now(timezone.utc) + timedelta(minutes=10))
    params = {
        'client_id': WHOP_OAUTH_CLIENT_ID,
        'redirect_uri': WHOP_OAUTH_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'openid profile',
        'state': state,
        'code_challenge': _pkce_challenge(verifier),
        'code_challenge_method': 'S256',
    }
    return f'{OAUTH_BASE}/authorize?{urlencode(params)}'

async def exchange_code(code: str, state: str) -> tuple[int, str]:
    row = database.consume_oauth_state(state)
    if not row: raise ValueError('oauth_state_invalid_or_expired')
    if not _valid_state(state, row.telegram_id): raise ValueError('oauth_state_invalid')
    payload = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': WHOP_OAUTH_REDIRECT_URI,
        'client_id': WHOP_OAUTH_CLIENT_ID,
        'client_secret': WHOP_OAUTH_CLIENT_SECRET,
        'code_verifier': row.code_verifier,
    }
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.post(f'{OAUTH_BASE}/token', data=payload, headers={'Content-Type': 'application/x-www-form-urlencoded'}) as r:
            token = await r.json(content_type=None)
            if r.status >= 300: raise RuntimeError(f'whop_oauth_token_{r.status}')
        access_token = str(token.get('access_token') or '')
        if not access_token: raise RuntimeError('whop_oauth_missing_access_token')
        async with s.get(f'{OAUTH_BASE}/userinfo', headers={'Authorization': f'Bearer {access_token}'}) as r:
            userinfo = await r.json(content_type=None)
            if r.status >= 300: raise RuntimeError(f'whop_oauth_userinfo_{r.status}')
    whop_user_id = str(userinfo.get('sub') or '')
    if not whop_user_id: raise RuntimeError('whop_oauth_missing_user_id')
    return row.telegram_id, whop_user_id

def product_url() -> str:
    return WHOP_PRODUCT_URL
