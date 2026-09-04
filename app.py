from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from telegram import Update

import access
import database
import market
import whop
from bot import build_application
from config import BELMO_PUBLIC_URL, TELEGRAM_WEBHOOK_SECRET, LOG_LEVEL, MARKET_POLL_SECONDS, WHOP_COMPANY_ID, WHOP_PRODUCT_ID, validate

logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format='%(asctime)s %(levelname)s %(name)s: %(message)s')
stop_event = asyncio.Event()
telegram_app = None
market_task = None


def _dt(value: str | None) -> datetime | None:
    if not value: return None
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

async def process_whop(data: dict) -> None:
    event = str(data.get('type') or data.get('event') or '').strip()
    event_id = str(data.get('_webhook_id') or data.get('id') or '').strip()
    if not event_id: raise ValueError('webhook_identity_missing')
    if not await asyncio.to_thread(database.record_webhook_event, event_id, event): return

    payload = data.get('data') or data.get('payload') or {}
    company_id = str(data.get('company_id') or payload.get('company', {}).get('id') or '').strip()
    if company_id and company_id != WHOP_COMPANY_ID: raise ValueError('whop_company_mismatch')

    if event not in {'membership.activated', 'membership.deactivated', 'membership.updated', 'membership.cancelled', 'membership.canceled', 'payment.refunded', 'refund.created', 'refund.completed'}:
        return

    membership_id = str(payload.get('id') or payload.get('membership_id') or '').strip()
    user = payload.get('user') or {}
    whop_user_id = str(user.get('id') or payload.get('user_id') or '').strip()
    product_id = str((payload.get('product') or {}).get('id') or '').strip()
    if event.startswith('membership.'):
        if not membership_id or not whop_user_id: raise ValueError('membership_identity_missing')
        if product_id and product_id != WHOP_PRODUCT_ID: return
        status = str(payload.get('status') or ('active' if event == 'membership.activated' else 'canceled')).lower()
        await asyncio.to_thread(database.sync_membership, membership_id, whop_user_id, status, _dt(payload.get('renewal_period_start')), _dt(payload.get('renewal_period_end')), product_id or WHOP_PRODUCT_ID)
        return

    # Refunds are not used to create entitlement. If Whop includes the membership ID,
    # fail closed locally until the membership lifecycle webhook confirms its new state.
    if membership_id:
        await asyncio.to_thread(database.deactivate_membership, membership_id, 'refunded')


@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app, market_task
    validate()
    await asyncio.to_thread(database.init_db)
    telegram_app = build_application()
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.bot.set_webhook(url=f'{BELMO_PUBLIC_URL}/telegram/webhook', secret_token=TELEGRAM_WEBHOOK_SECRET, drop_pending_updates=False)
    market_task = asyncio.create_task(market.run_poller(stop_event))
    yield
    stop_event.set()
    if market_task:
        await market_task
    await telegram_app.bot.delete_webhook(drop_pending_updates=False)
    await telegram_app.stop()
    await telegram_app.shutdown()

app = FastAPI(title='Neural Gold', version='2.0.0', lifespan=lifespan)

@app.get('/health')
async def health():
    checks = {'database': False, 'market': False, 'telegram': False}
    try:
        await asyncio.to_thread(database.db_ping); checks['database'] = True
    except Exception: logging.getLogger('app').exception('health database check failed')
    try:
        sample = await asyncio.to_thread(database.latest_sample)
        if sample:
            ts = sample['ts'] if sample['ts'].tzinfo else sample['ts'].replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - ts).total_seconds()
            checks['market'] = 0 <= age <= max(180, MARKET_POLL_SECONDS * 3)
    except Exception: logging.getLogger('app').exception('health market check failed')
    if telegram_app is not None:
        try:
            await telegram_app.bot.get_me(); checks['telegram'] = True
        except Exception: logging.getLogger('app').exception('health telegram check failed')
    return {'ok': all(checks.values()), 'service': 'neural-gold', 'checks': checks}

@app.get('/auth/whop/callback', response_class=HTMLResponse)
async def whop_oauth_callback(code: str | None = None, state: str | None = None, error: str | None = None):
    if error: return HTMLResponse('<h2>Whop linking was cancelled.</h2><p>Return to Telegram and try again.</p>', status_code=400)
    if not code or not state: return HTMLResponse('<h2>Invalid Whop callback.</h2>', status_code=400)
    try:
        telegram_id, whop_user_id = await whop.exchange_code(code, state)
        await asyncio.to_thread(database.ensure_user, telegram_id)
        await asyncio.to_thread(database.link_whop_user, telegram_id, whop_user_id)
        if telegram_app is not None:
            await telegram_app.bot.send_message(telegram_id, '✅ Akun Whop berhasil terhubung. Jika membership Anda ACTIVE dan Anda sudah menjadi member channel premium, akses Neural Gold akan tersedia otomatis.')
        return HTMLResponse('<h2>Whop account linked.</h2><p>You can return to Telegram and check Status Akses.</p>')
    except ValueError as exc:
        return HTMLResponse(f'<h2>Whop linking failed.</h2><p>{str(exc)}</p>', status_code=400)
    except Exception:
        logging.getLogger('app').exception('whop oauth callback failed')
        return HTMLResponse('<h2>Whop linking failed.</h2><p>Please return to Telegram and try again.</p>', status_code=500)

@app.post('/telegram/webhook')
async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: str | None = Header(default=None)):
    if x_telegram_bot_api_secret_token != TELEGRAM_WEBHOOK_SECRET: raise HTTPException(403, 'invalid_secret')
    if telegram_app is None: raise HTTPException(503, 'telegram_not_ready')
    try:
        update = Update.de_json(await request.json(), telegram_app.bot)
        await telegram_app.process_update(update)
        return {'ok': True}
    except Exception as exc: raise HTTPException(400, 'invalid_update') from exc

@app.post('/webhooks/whop')
async def whop_webhook(request: Request):
    try: data = whop.verify_webhook(await request.body(), request.headers)
    except Exception as exc: raise HTTPException(400, 'invalid_webhook') from exc
    try: await process_whop(data)
    except ValueError as exc: raise HTTPException(400, str(exc)) from exc
    return {'ok': True}
