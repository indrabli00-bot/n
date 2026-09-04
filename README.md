# NEURAL GOLD — Production Core

Production service for premium XAU/USD market information distributed through Telegram and sold through Whop.

## Core
- FastAPI HTTP service
- Telegram webhook with secret validation
- Whop webhook verification with atomic, idempotent membership entitlement sync
- GoldAPI spot polling every 60 seconds
- PostgreSQL persistence
- Conservative signal engine with explicit HOLD/DATA_GAP states
- Automatic Premium Channel publication for actionable LONG/SHORT signals
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
`GoldAPI → Market Samples → Signal Engine → automatic LONG/SHORT publication → Premium Channel`

There is no human approval command and no `/approve` gate. `HOLD` and `DATA_GAP` are not published. Repeated signals in the same direction are suppressed to prevent channel spam; a new direction can be published when the engine changes direction.

### Premium Bot
`Active access → on-demand signal calculation → Telegram Bot`

The bot may calculate and show the current signal independently to an entitled user. This is separate from automatic Premium Channel publication.

## Access
`ACTIVE Whop membership AND Telegram premium-channel membership → PREMIUM ACCESS`

Whop is the payment and entitlement authority. The database only mirrors Whop membership events and does not create entitlement independently.

## Environment
Copy `.env.example` to `.env` locally or configure the same variables in the hosting service. Never commit real credentials.

The first deployment intentionally stays in `HOLD / DATA_GAP` until at least 300 one-minute market samples are collected. The service does not execute trades or manage customer funds. Signals are market information/education, not personal financial advice.
