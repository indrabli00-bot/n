# NEURAL GOLD v3.2 — Belmo Production Deployment

The production deployment contract is maintained in `DEPLOY_BELMO.md`.

## Runtime

- Start command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
- Telegram transport: FastAPI webhook at `/telegram/webhook`
- Whop webhook: `/webhooks/whop`
- Health: `/health` (HTTP 200 only when the Telegram application is running)
- Database: external persistent PostgreSQL for paid production

## Required environment variables

```text
TELEGRAM_BOT_TOKEN=...
ADMIN_TELEGRAM_ID=...
BELMO_PUBLIC_URL=https://YOUR-BELMO-DOMAIN
TELEGRAM_WEBHOOK_SECRET=...
GOLDAPI_API_KEY=...
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DATABASE
WHOP_API_KEY=...
WHOP_WEBHOOK_SECRET=...
LOG_LEVEL=INFO
```

`GOLDAPI_API_KEY` is the only market-data API credential. TwelveData is not part of the runtime contract.

## Market-data readiness

GoldAPI.io supplies the live XAU/USD spot price and daily historical data. It does not provide native M5/M15 candles in the documented API contract. NEURAL GOLD therefore builds M5/M15 bars only from persisted live GoldAPI samples collected every 60 seconds. No synthetic or historical candle backfill is created. After a fresh deployment, NEURAL STRIKES remains `HOLD / DATA_GAP` until sufficient contiguous samples exist for its requested lookback.

## Production rule

Do not redeploy until the final `main` commit has a green Phase 2 CI run and Belmo `/health` reports `telegram: true`.

See `DEPLOY_BELMO.md` for the complete pre-redeploy checklist.
