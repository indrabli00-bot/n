# NEURAL GOLD v3.2 — Phase 2 Status

## Current state

**READY FOR BELMO REDEPLOY after final CI verification.**

Production code is on `main`. The runtime uses `app.py` with Telegram and Whop webhooks, strict allow-listed plan validation, idempotent fulfillment, notification recovery, and the canonical customer UI contract.

## Required deployment state

- Belmo start: `uvicorn app:app --host 0.0.0.0 --port $PORT`
- Persistent PostgreSQL database
- `BELMO_PUBLIC_URL`
- `TELEGRAM_WEBHOOK_SECRET`
- `WHOP_API_KEY`
- `WHOP_WEBHOOK_SECRET`
- `GOLDAPI_API_KEY`
- `TWELVEDATA_API_KEY`

Do not mark the deployment healthy until `/health` reports `telegram: true`.
