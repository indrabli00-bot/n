import os
import sys
from pathlib import Path

# Establish deterministic test configuration before any application module is
# imported.  Several modules intentionally snapshot environment values at
# import time, so setting these only inside an individual test module is too
# late when pytest collects modules in a different order.
TEST_ENV = {
    'TELEGRAM_BOT_TOKEN': 'test-token',
    'TELEGRAM_PREMIUM_CHAT_ID': '-1001234567890',
    'TELEGRAM_WEBHOOK_SECRET': 'telegram-secret',
    'BELMO_PUBLIC_URL': 'https://example.test',
    'DATABASE_URL': 'sqlite:///./test.sqlite',
    'GOLDAPI_API_KEY': 'gold-test-key',
    'WHOP_COMPANY_ID': 'biz_neural_gold',
    'WHOP_PRODUCT_ID': 'prod_neural_gold',
    'WHOP_WEBHOOK_SECRET': 'whsec_test',
    'WHOP_OAUTH_CLIENT_ID': 'oauth-client-test',
    'WHOP_OAUTH_CLIENT_SECRET': 'oauth-secret-test',
    'WHOP_OAUTH_REDIRECT_URI': 'https://example.test/auth/whop/callback',
    'WHOP_OAUTH_STATE_SECRET': 'state_test',
    'ADMIN_TELEGRAM_ID': '999',
    'MARKET_POLL_SECONDS': '60',
    'MIN_MARKET_SAMPLES': '300',
}

for key, value in TEST_ENV.items():
    os.environ.setdefault(key, value)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
