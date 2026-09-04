import asyncio
import os
from urllib.parse import parse_qs, urlparse

os.environ.setdefault('DATABASE_URL', 'sqlite:///./test_whop.sqlite')
os.environ.setdefault('WHOP_OAUTH_CLIENT_ID', 'app_test')
os.environ.setdefault('WHOP_OAUTH_CLIENT_SECRET', 'secret_test')
os.environ.setdefault('WHOP_OAUTH_REDIRECT_URI', 'https://example.com/auth/whop/callback')
os.environ.setdefault('WHOP_OAUTH_STATE_SECRET', 'state_test')
os.environ.setdefault('WHOP_PRODUCT_URL', 'https://whop.com/example/product/')
os.environ.setdefault('WHOP_WEBHOOK_SECRET', 'whsec_test')

import database
import whop


def test_authorize_request_includes_oidc_nonce(monkeypatch):
    captured = {}

    def save_state(state, telegram_id, verifier, expires_at):
        captured.update(state=state, telegram_id=telegram_id, verifier=verifier)

    monkeypatch.setattr(database, 'save_oauth_state', save_state)
    url = asyncio.run(whop.create_link_url(12345))
    params = parse_qs(urlparse(url).query)

    assert params['scope'] == ['openid profile']
    assert params['nonce']
    assert params['state'] == [captured['state']]
    assert params['code_challenge_method'] == ['S256']


def test_oauth_state_binds_telegram_id():
    state = whop._signed_state(12345, 'nonce-test')
    assert whop._valid_state(state, 12345) is True
    assert whop._valid_state(state, 54321) is False
