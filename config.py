from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')


def env(name: str, default: str = '') -> str:
    return os.getenv(name, default).strip()


def int_env(name: str, default: int) -> int:
    raw = env(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f'Invalid integer environment variable: {name}') from exc
    return value


TELEGRAM_BOT_TOKEN = env('TELEGRAM_BOT_TOKEN')
TELEGRAM_PREMIUM_CHAT_ID = int_env('TELEGRAM_PREMIUM_CHAT_ID', 0)
TELEGRAM_WEBHOOK_SECRET = env('TELEGRAM_WEBHOOK_SECRET')
BELMO_PUBLIC_URL = env('BELMO_PUBLIC_URL').rstrip('/')
DATABASE_URL = env('DATABASE_URL')
GOLDAPI_API_KEY = env('GOLDAPI_API_KEY')
WHOP_COMPANY_ID = env('WHOP_COMPANY_ID')
WHOP_PRODUCT_ID = env('WHOP_PRODUCT_ID')
WHOP_WEBHOOK_SECRET = env('WHOP_WEBHOOK_SECRET')
WHOP_OAUTH_CLIENT_ID = env('WHOP_OAUTH_CLIENT_ID')
WHOP_OAUTH_CLIENT_SECRET = env('WHOP_OAUTH_CLIENT_SECRET')
WHOP_OAUTH_REDIRECT_URI = env(
    'WHOP_OAUTH_REDIRECT_URI',
    f'{BELMO_PUBLIC_URL}/auth/whop/callback',
)
WHOP_OAUTH_STATE_SECRET = env('WHOP_OAUTH_STATE_SECRET')
LOG_LEVEL = env('LOG_LEVEL', 'INFO').upper()
MARKET_POLL_SECONDS = int_env('MARKET_POLL_SECONDS', 60)
MIN_MARKET_SAMPLES = int_env('MIN_MARKET_SAMPLES', 300)


def validate() -> None:
    required = {
        'TELEGRAM_BOT_TOKEN': TELEGRAM_BOT_TOKEN,
        'TELEGRAM_PREMIUM_CHAT_ID': str(TELEGRAM_PREMIUM_CHAT_ID),
        'TELEGRAM_WEBHOOK_SECRET': TELEGRAM_WEBHOOK_SECRET,
        'BELMO_PUBLIC_URL': BELMO_PUBLIC_URL,
        'DATABASE_URL': DATABASE_URL,
        'GOLDAPI_API_KEY': GOLDAPI_API_KEY,
        'WHOP_COMPANY_ID': WHOP_COMPANY_ID,
        'WHOP_PRODUCT_ID': WHOP_PRODUCT_ID,
        'WHOP_WEBHOOK_SECRET': WHOP_WEBHOOK_SECRET,
        'WHOP_OAUTH_CLIENT_ID': WHOP_OAUTH_CLIENT_ID,
        'WHOP_OAUTH_CLIENT_SECRET': WHOP_OAUTH_CLIENT_SECRET,
        'WHOP_OAUTH_REDIRECT_URI': WHOP_OAUTH_REDIRECT_URI,
        'WHOP_OAUTH_STATE_SECRET': WHOP_OAUTH_STATE_SECRET,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise RuntimeError(
            'Missing required environment variables: ' + ', '.join(missing)
        )
    if TELEGRAM_PREMIUM_CHAT_ID == 0:
        raise RuntimeError('TELEGRAM_PREMIUM_CHAT_ID must be non-zero')
    if MARKET_POLL_SECONDS <= 0:
        raise RuntimeError('MARKET_POLL_SECONDS must be greater than zero')
    if MIN_MARKET_SAMPLES < 50:
        raise RuntimeError('MIN_MARKET_SAMPLES must be at least 50')
