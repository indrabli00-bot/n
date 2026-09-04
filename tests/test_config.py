def test_env_names_documented():
    required = [
        'TELEGRAM_BOT_TOKEN', 'ADMIN_TELEGRAM_ID', 'BELMO_PUBLIC_URL',
        'DATABASE_URL', 'GOLDAPI_API_KEY', 'TELEGRAM_PREMIUM_CHAT_ID',
        'TELEGRAM_WEBHOOK_SECRET', 'WHOP_COMPANY_ID', 'WHOP_PRODUCT_ID',
        'WHOP_PRODUCT_URL', 'WHOP_WEBHOOK_SECRET', 'WHOP_OAUTH_CLIENT_ID',
        'WHOP_OAUTH_CLIENT_SECRET', 'WHOP_OAUTH_REDIRECT_URI',
        'WHOP_OAUTH_STATE_SECRET',
    ]
    text = open('.env.example').read()
    assert all(k + '=' in text for k in required)
    assert 'WHOP_API_KEY=' not in text
