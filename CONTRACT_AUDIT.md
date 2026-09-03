# NEURAL GOLD v3.2 — Contract Audit Baseline

The production contract is enforced at the `app.py` boundary and by the Phase 2 CI suite.

## Runtime contract

- Production entry point: `app:app`
- Telegram transport: FastAPI webhook
- Startup fails closed without `BELMO_PUBLIC_URL`, `TELEGRAM_WEBHOOK_SECRET`, `WHOP_API_KEY`, or `WHOP_WEBHOOK_SECRET`.
- Telegram webhook registration failure aborts startup.
- Telegram webhook registration preserves pending updates across restarts.
- `/health` is only considered production-ready when `telegram` is `true`.

## Customer UI contract

- Persistent navigation: `🏠 Menu` and `👨‍💼 Account` (localized through `i18n.py`).
- Header status is rendered from the localization table with `🟢` / `🔴` state icons.
- Customer module labels remain `MARKET PULSE`, `NEURAL STRIKES`, and `STRUCTURE MAP`.
- Premium access uses exactly 7 / 14 / 30 day plans.
- Legacy `phase2_bot.py` UI routes are removed; it is checkout-link infrastructure only.

## Market-data contract

- `GOLDAPI_API_KEY` is the only market-data API credential.
- The runtime contains no TwelveData credential or endpoint.
- Live XAU/USD spot data comes from GoldAPI.io, with the existing keyless live-price fallback cascade only for price-display continuity.
- M5/M15 SMC candles are built only from persisted live GoldAPI samples; no synthetic or historical candle backfill is allowed.
- If contiguous M5/M15 coverage is not available, NEURAL STRIKES fails closed to `HOLD / DATA_GAP`.

## Payment contract

- Whop payment identity is verified before fulfillment.
- Plan IDs are allow-listed; unknown plans never inherit a fallback duration.
- `metadata.plan_days`, Whop plan ID, and stored order duration must agree.
- A Whop payment cannot create a second local order after it is already bound.
- Fulfillment is fenced and idempotent.
- Customer notification is decoupled from entitlement activation and is recoverable.
- Local `/reconcile` does not grant a new entitlement without a fulfillment claim; otherwise remote Whop revalidation is required.

## Regression contract

Every `main` push must pass:

1. Python compilation
2. Production contract guard
3. UI hardcode guard
4. Pytest
5. Full unittest discovery

No redeploy should be considered ready while the final `main` commit is not green.
