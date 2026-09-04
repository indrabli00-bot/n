# NEURAL GOLD — Production Core

Production service for premium XAU/USD market information distributed through Telegram and sold through Whop.

## Core
- FastAPI HTTP service
- Telegram webhook with secret validation
- Whop webhook verification with atomic, idempotent membership entitlement sync
- GoldAPI spot polling every 60 seconds
- PostgreSQL persistence
- Conservative signal engine with explicit HOLD/DATA_GAP states
- Premium Channel publication is gated by explicit human approval
- Premium access requires an ACTIVE Whop membership and Telegram channel membership
- Telegram bot does not process purchases or sell subscription packages

## Start
`uvicorn app:app --host 0.0.0.0 --port $PORT`

## Endpoints
- `GET /health`
- `POST /telegram/webhook`
- `POST /webhooks/whop`

## Signal flows

### Premium Channel
`Market data → signal engine candidate → human approval (/approve) → Premium Channel`

Only the admin identified by `ADMIN_TELEGRAM_ID` can execute `/approve`. The candidate is persisted as an approved signal and then sent to `TELEGRAM_PREMIUM_CHAT_ID`. There is no automatic candidate-to-channel publisher.

### Premium Bot
`Active access → on-demand signal calculation → Telegram Bot`

The bot may calculate and show a signal independently to an entitled user. This is separate from the Premium Channel publication gate.

## Access
`ACTIVE Whop membership AND Telegram premium-channel membership → PREMIUM ACCESS`

Whop is the payment and entitlement authority. The database only mirrors Whop membership events and does not create entitlement independently.

## Environment
Copy `.env.example` to `.env` locally or configure the same variables in the hosting service. Never commit real credentials.

The first deployment intentionally stays in `HOLD / DATA_GAP` until at least 300 one-minute market samples are collected. The service does not execute trades or manage customer funds. Signals are market information/education, not personal financial advice.
