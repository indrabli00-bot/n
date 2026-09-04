from __future__ import annotations
import asyncio, logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException, Request
from telegram import Update
import database, market, whop
from bot import build_application
from config import BELMO_PUBLIC_URL, TELEGRAM_WEBHOOK_SECRET, LOG_LEVEL, validate

logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format='%(asctime)s %(levelname)s %(name)s: %(message)s')
stop_event = asyncio.Event(); telegram_app = None; market_task = None

async def notify_customer(telegram_id: int, days: int) -> None:
    if telegram_app is None: return
    user = database.get_user(telegram_id)
    expiry = user.subscription_expiry.isoformat() if user else '-'
    text = ('<b>✅ PEMBAYARAN TERVERIFIKASI</b>\n\n'
            f'Akses Neural Gold selama <b>{days} hari</b> telah aktif.\n'
            f'EXPIRES: {expiry}\n\n'
            'Gunakan menu <b>📡 Sinyal Terbaru</b> untuk melihat kondisi pasar.\n'
            'Pastikan Anda juga sudah bergabung di private channel premium.\n\n'
            '<i>Market information & education only. Not personal financial advice. Trading involves risk.</i>')
    try:
        await telegram_app.bot.send_message(telegram_id, text, parse_mode='HTML')
    except Exception:
        logging.getLogger('app').exception('customer notification failed')

async def process_whop(data: dict) -> None:
    event = str(data.get('event') or data.get('type') or '')
    payload = data.get('data') or data.get('payload') or {}
    if event == 'payment.succeeded':
        md = payload.get('metadata') or {}
        order_id, payment_id = str(md.get('neural_order_id') or ''), str(payload.get('id') or '')
        if not order_id or not payment_id: raise ValueError('payment_identity_missing')
        order = database.get_order(order_id)
        if not order: raise ValueError('order_not_found')
        if str(md.get('telegram_id') or '') and int(md['telegram_id']) != order.telegram_id: raise ValueError('telegram_identity_mismatch')
        if str(md.get('plan_days') or '') and int(md['plan_days']) != order.duration_days: raise ValueError('plan_duration_mismatch')
        changed = database.fulfill(payment_id, order_id)
        if changed: await notify_customer(order.telegram_id, order.duration_days)
        return
    md = payload.get('metadata') or {}
    order_id = str(md.get('neural_order_id') or '')
    if not order_id and payload.get('id'):
        order = database.get_order_by_payment(str(payload['id'])); order_id = order.id if order else ''
    if event == 'membership.deactivated' and order_id:
        order = database.get_order(order_id)
        if order: database.deactivate_subscription(order.telegram_id)
        database.update_order(order_id, status=event)
    elif event in {'refund.created', 'refund.updated'} and order_id:
        database.update_order(order_id, status=event)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app, market_task
    validate(); database.init_db()
    telegram_app = build_application(); await telegram_app.initialize(); await telegram_app.start()
    await telegram_app.bot.set_webhook(url=f'{BELMO_PUBLIC_URL}/telegram/webhook', secret_token=TELEGRAM_WEBHOOK_SECRET, drop_pending_updates=False)
    market_task = asyncio.create_task(market.run_poller(stop_event))
    yield
    stop_event.set()
    if market_task: await market_task
    await telegram_app.bot.delete_webhook(drop_pending_updates=False)
    await telegram_app.stop(); await telegram_app.shutdown()

app = FastAPI(title='Neural Gold', version='1.1.0', lifespan=lifespan)

@app.get('/health')
async def health(): return {'ok': True, 'service': 'neural-gold', 'telegram': telegram_app is not None}

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
