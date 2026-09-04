# NEURAL GOLD — Production Core

Production service for premium XAU/USD market information distributed through Telegram and sold through Whop.

## Core
- FastAPI HTTP service
- Telegram webhook with secret validation
- Whop webhook verification with atomic, idempotent membership entitlement sync
- GoldAPI spot polling every 60 seconds
- PostgreSQL persistence
- Conservative signal engine with explicit HOLD/DATA_GAP states
- Premium access requires an ACTIVE Whop membership and Telegram channel membership

## Start
`uvicorn app:app --host 0.0.0.0 --port $PORT`

## Endpoints
- `GET /health`
- `POST /telegram/webhook`
- `POST /webhooks/whop`

## Environment
Copy `.env.example` to `.env` locally or configure the same variables in the hosting service. Never commit real credentials.

The first deployment intentionally stays in `HOLD / DATA_GAP` until at least 300 one-minute market samples are collected. The service does not execute trades or manage customer funds. Signals are market information/education, not personal financial advice.
