# NEURAL GOLD v3.2 — Belmo Production Deployment

## Runtime

- Service: Python HTTP service
- Start command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
- Telegram transport: custom FastAPI webhook
- Production webhook: `POST /telegram/webhook`
- Whop webhook: `POST /webhooks/whop`
- Health: `GET /health`

The production entry point is `app.py`. `main.py` is the **single canonical customer Telegram UI/controller**. `app.py` owns HTTP/webhook transport; service modules own market data, authentication, database, and Whop operations. There is no second customer UI contract installed at runtime.

## Required Belmo environment variables

Set these in Belmo. Never commit real secrets.

```text
TELEGRAM_BOT_TOKEN=...
ADMIN_TELEGRAM_ID=...
BELMO_PUBLIC_URL=https://YOUR-BELMO-DOMAIN
TELEGRAM_WEBHOOK_SECRET=...
GOLDAPI_API_KEY=...
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DATABASE
WHOP_API_KEY=...
WHOP_COMPANY_ID=...
WHOP_WEBHOOK_SECRET=...
LOG_LEVEL=INFO
```

`GOLDAPI_API_KEY` is the only market-price API credential required by the runtime. TwelveData is not used and must not be configured.

`BELMO_PUBLIC_URL`, `TELEGRAM_WEBHOOK_SECRET`, `WHOP_API_KEY`, and `WHOP_WEBHOOK_SECRET` are mandatory for the production Phase 2 runtime. Startup fails closed if any is missing.

## Startup sequence

1. Validate production secrets and public URL.
2. Initialize the application database, Phase 2 Whop storage, and GoldAPI candle sample storage.
3. Install runtime hardening.
4. Build the Telegram application from the canonical `main.py` controller. The dedicated fast `/start` adapter is only a latency mechanism; it does not replace the canonical UI/controller.
5. Initialize/start the Telegram application.
6. Register the Telegram webhook at `/telegram/webhook` without dropping queued updates.
7. Start expiry, fulfillment recovery, and the 60-second GoldAPI market-sample job.

If Telegram webhook registration fails, startup is aborted instead of leaving a superficially healthy HTTP service with a non-working bot.

## Telegram flow

1. Customer sends `/start`.
2. The fast path responds immediately; database/auth finalization runs without blocking the initial response.
3. The canonical `main.py` UI remains the single source for customer navigation and module rendering.
4. Inactive customer sees the premium access screen.
5. Customer chooses 7D / 14D / 30D.
6. The signed checkout link creates a real Whop checkout.
7. `payment.succeeded` is verified by signature and allow-listed plan ID.
8. Fulfillment activates the Telegram account atomically and idempotently.
9. Customer notification is delivered independently; failed notification remains recoverable.

## Market data

`GOLDAPI_API_KEY` is used for the primary XAU/USD live price feed. The runtime does not require a TwelveData credential. If the primary feed is unavailable, the existing keyless fallback cascade is used according to the price-source contract; no fabricated price is generated.

GoldAPI does not provide native M5/M15 candles in the documented API contract. NEURAL GOLD therefore stores one real GoldAPI spot sample per minute and aggregates only contiguous sampled data into M5/M15 bars. The current SMC lookback is 60 M5 bars plus 20 M15 bars, so a fresh deployment needs approximately 5 hours of contiguous samples before NEURAL STRIKES can leave `HOLD / DATA_GAP`. This is deliberate fail-closed behavior, not a fabricated historical backfill.

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
- [ ] Only the documented environment variables are configured; no `TWELVEDATA_API_KEY` is required
- [ ] `GOLDAPI_API_KEY` is configured with a valid GoldAPI.io key
- [ ] `DATABASE_URL` points to the production PostgreSQL database
- [ ] Telegram webhook secret matches the value configured in the deployment
- [ ] Whop API key is active and has the permissions required by the checkout/revalidation endpoints
- [ ] Whop company ID is configured when using company validation
- [ ] Whop webhook secret matches the Whop webhook configuration
- [ ] Whop webhook URL is `https://<BELMO_PUBLIC_URL>/webhooks/whop`
- [ ] Telegram webhook URL is `https://<BELMO_PUBLIC_URL>/telegram/webhook`
- [ ] `/health` reports `telegram: true` after startup
- [ ] GitHub Actions Phase 2 CI is green on the final `main` commit
