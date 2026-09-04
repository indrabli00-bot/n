def test_env_names_documented():
    required = ['TELEGRAM_BOT_TOKEN','ADMIN_TELEGRAM_ID','BELMO_PUBLIC_URL','DATABASE_URL','GOLDAPI_API_KEY','TELEGRAM_PREMIUM_CHAT_ID','TELEGRAM_WEBHOOK_SECRET','WHOP_API_KEY','WHOP_COMPANY_ID','WHOP_WEBHOOK_SECRET']
    text = open('.env.example').read()
    assert all(k + '=' in text for k in required)
