# NEURAL GOLD v3.2 — Belmo Production Deployment

## Runtime

- Service: Python HTTP service
- Start command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
- Telegram transport: custom FastAPI webhook
- Production webhook: `POST /telegram/webhook`
- Whop webhook: `POST /webhooks/whop`
- Health: `GET /health`

The production entry point is `app.py`. `main.py` is retained for local polling/development only.

## Required Belmo environment variables

Set these in Belmo. Never commit real secrets.

```text
TELEGRAM_BOT_TOKEN=...
ADMIN_TELEGRAM_ID=...
BELMO_PUBLIC_URL=https://YOUR-BELMO-DOMAIN
TELEGRAM_WEBHOOK_SECRET=...
GOLDAPI_API_KEY=...
TWELVEDATA_API_KEY=...
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DATABASE
WHOP_API_KEY=...
WHOP_WEBHOOK_SECRET=...
LOG_LEVEL=INFO
```

`BELMO_PUBLIC_URL`, `TELEGRAM_WEBHOOK_SECRET`, `WHOP_API_KEY`, and `WHOP_WEBHOOK_SECRET` are mandatory for the production Phase 2 runtime. Startup fails closed if any is missing.

## Startup sequence

1. Validate production secrets and public URL.
2. Initialize the application database and Phase 2 Whop storage.
3. Install runtime hardening and the canonical customer UI contract.
4. Initialize/start the Telegram application.
5. Register the Telegram webhook at `/telegram/webhook`.
6. Start expiry and fulfillment recovery jobs.

If Telegram webhook registration fails, startup is aborted instead of leaving a superficially healthy HTTP service with a non-working bot.

## Telegram flow

1. Customer sends `/start`.
2. Inactive customer sees the premium access screen.
3. Customer chooses 7D / 14D / 30D.
4. The signed checkout link creates a real Whop checkout.
5. `payment.succeeded` is verified by signature and allow-listed plan ID.
6. Fulfillment activates the Telegram account atomically and idempotently.
7. Customer notification is delivered independently; failed notification remains recoverable.

## Whop recovery

- Duplicate webhook events are fenced.
- Stale fulfillment claims can be recovered.
- Remote `/reconcile` revalidates payment state against Whop before creating a new local entitlement.
- Unknown plan IDs and plan-duration mismatches are rejected.
- A payment already bound to a local order is never used to create a second order.
- Customer notification failure does not roll back a successful entitlement.

## Database

Use an external persistent PostgreSQL database for paid production. SQLite is appropriate for local tests only; container-local SQLite storage is not a durable production subscription store.

## Pre-redeploy checklist

- [ ] Belmo start command is exactly `uvicorn app:app --host 0.0.0.0 --port $PORT`
- [ ] All required environment variables are configured
- [ ] `DATABASE_URL` points to the production PostgreSQL database
- [ ] Telegram webhook secret matches the value configured in the deployment
- [ ] Whop webhook secret matches the Whop webhook configuration
- [ ] Whop API key is active and has the permissions required by the checkout/revalidation endpoints
- [ ] Whop webhook URL is `https://<BELMO_PUBLIC_URL>/webhooks/whop`
- [ ] Telegram webhook URL is `https://<BELMO_PUBLIC_URL>/telegram/webhook`
- [ ] `/health` reports `telegram: true` after startup
- [ ] GitHub Actions Phase 2 CI is green on the final `main` commit
