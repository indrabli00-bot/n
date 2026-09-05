# NEURAL GOLD — Production Core

Production service for premium XAU/USD market information distributed through Telegram and sold through Whop.

## Core
- FastAPI HTTP service
- Telegram webhook with secret validation and update idempotency
- Whop webhook verification with atomic, idempotent membership entitlement sync
- GoldAPI spot polling every 60 seconds
- PostgreSQL persistence
- Conservative signal engine with explicit HOLD/DATA_GAP states
- Automatic Premium Channel publication for actionable LONG/SHORT signals
- Premium Channel is the primary customer product
- Telegram bot is a bonus utility for existing Premium Channel members
- Telegram bot does not process purchases or sell subscription packages

## Start
`uvicorn app:app --host 0.0.0.0 --port $PORT`

## Endpoints
- `GET /health` — liveness/dependency status; does not require a fresh market sample
- `GET /ready` — readiness; returns HTTP 503 until database, Telegram, and fresh market data are available
- `POST /telegram/webhook`
- `POST /webhooks/whop`

## Signal flows

### Premium Channel
`Whop purchase → active membership → Premium Channel access → Neural Strikes`

The Premium Channel is the purchased destination. Automatic LONG/SHORT signals are published there. `HOLD` and `DATA_GAP` are not published. Repeated signals in the same direction are suppressed to prevent channel spam; a new direction can be published when the engine changes direction.

### Telegram Bot Bonus
`Premium Channel member → Telegram Bot bonus → on-demand signal / status / market information`

The bot is not the purchase gate, payment processor, or required Whop OAuth step. Normal member access to the bot is determined from Premium Channel membership. A member should not be asked to connect a Whop account just to use the bonus bot.

## Access model
`Whop ACTIVE membership → Premium Channel → Telegram bot bonus`

Whop is the payment and entitlement authority. Premium Channel access is the primary customer benefit. The bot is an additional member utility and does not replace the channel.

## Environment
Copy `.env.example` to `.env` locally or configure the same variables in the hosting service. Never commit real credentials.

The first deployment intentionally stays in `HOLD / DATA_GAP` until at least 300 one-minute market samples are collected. The service does not execute trades or manage customer funds. Signals are market information/education, not personal financial advice.
