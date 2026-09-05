from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from telegram import Update

import database
import market
import publisher
import whop
from bot import _format_signal, build_application
from config import (
    BELMO_PUBLIC_URL,
    LOG_LEVEL,
    MARKET_POLL_SECONDS,
    TELEGRAM_PREMIUM_CHAT_ID,
    TELEGRAM_WEBHOOK_SECRET,
    WHOP_COMPANY_ID,
    WHOP_PRODUCT_ID,
    validate,
)

log = logging.getLogger('app')
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)

stop_event = asyncio.Event()
telegram_app = None
market_task = None
TELEGRAM_COMPLETION_RETRIES = 3
SUPPORTED_MEMBERSHIP_EVENTS = {
    'membership.activated',
    'membership.deactivated',
    'membership.cancel_at_period_end_changed',
}


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def process_whop(data: dict) -> None:
    event_type = str(data.get('type') or '').strip().lower()
    if event_type not in SUPPORTED_MEMBERSHIP_EVENTS:
        return

    event_id = str(data.get('_webhook_id') or data.get('id') or '').strip()
    if not event_id:
        raise ValueError('webhook_identity_missing')

    payload = data.get('data') or {}
    if not isinstance(payload, dict):
        raise ValueError('webhook_payload_invalid')

    company = payload.get('company') or {}
    company_id = str(data.get('company_id') or company.get('id') or '').strip()
    if not company_id:
        raise ValueError('whop_company_missing')
    if company_id != WHOP_COMPANY_ID:
        raise ValueError('whop_company_mismatch')

    membership_id = str(payload.get('id') or '').strip()
    user = payload.get('user') or {}
    whop_user_id = str(user.get('id') or '').strip()
    product = payload.get('product') or {}
    product_id = str(product.get('id') or '').strip()

    if not membership_id or not whop_user_id:
        raise ValueError('membership_identity_missing')
    if not product_id:
        raise ValueError('membership_product_missing')
    if product_id != WHOP_PRODUCT_ID:
        return

    status = str(payload.get('status') or '').strip().lower()
    if event_type == 'membership.activated':
        status = 'active'
    elif event_type == 'membership.deactivated':
        status = 'inactive'
    elif not status:
        raise ValueError('membership_status_missing')

    source_updated_at = _dt(payload.get('updated_at') or payload.get('created_at'))
    await asyncio.to_thread(
        database.apply_membership_event,
        event_id,
        event_type,
        membership_id,
        whop_user_id,
        status,
        _dt(payload.get('renewal_period_start')),
        _dt(payload.get('renewal_period_end')),
        product_id,
        source_updated_at,
    )


async def evaluate_signal() -> None:
    if telegram_app is None:
        return
    await publisher.evaluate_and_publish(
        telegram_app.bot,
        TELEGRAM_PREMIUM_CHAT_ID,
        _format_signal,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global market_task, stop_event, telegram_app

    validate()
    await asyncio.to_thread(database.init_db)
    await asyncio.to_thread(publisher.init_state)
    stop_event = asyncio.Event()

    telegram_app = build_application()
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.bot.set_webhook(
        url=f'{BELMO_PUBLIC_URL}/telegram/webhook',
        secret_token=TELEGRAM_WEBHOOK_SECRET,
        drop_pending_updates=False,
    )

    market_task = asyncio.create_task(
        market.run_poller(stop_event, on_tick=evaluate_signal)
    )
    try:
        yield
    finally:
        stop_event.set()
        if market_task:
            try:
                await asyncio.wait_for(market_task, timeout=20)
            except asyncio.TimeoutError:
                log.warning('market poller did not stop cleanly; cancelling')
                market_task.cancel()
                await asyncio.gather(market_task, return_exceptions=True)
        if telegram_app is not None:
            await telegram_app.bot.delete_webhook(drop_pending_updates=False)
            await telegram_app.stop()
            await telegram_app.shutdown()
        market_task = None
        telegram_app = None


app = FastAPI(title='Neural Gold', version='2.0.0', lifespan=lifespan)


@app.get('/')
async def root():
    """Provide a lightweight 200 endpoint for platform and proxy probes."""
    return {'ok': True, 'service': 'neural-gold'}


async def _service_checks(require_market: bool) -> dict[str, bool]:
    checks = {'database': False, 'telegram': False}
    if require_market:
        checks['market'] = False

    try:
        await asyncio.to_thread(database.db_ping)
        checks['database'] = True
    except Exception:
        log.exception('database readiness check failed')

    if telegram_app is not None:
        try:
            await telegram_app.bot.get_me()
            checks['telegram'] = True
        except Exception:
            log.exception('telegram readiness check failed')

    if require_market:
        try:
            sample = await asyncio.to_thread(database.latest_sample)
            if sample:
                ts = sample['ts']
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - ts).total_seconds()
                checks['market'] = 0 <= age <= max(180, MARKET_POLL_SECONDS * 3)
        except Exception:
            log.exception('market readiness check failed')

    return checks


@app.get('/health')
async def health():
    checks = await _service_checks(require_market=False)
    return {'ok': all(checks.values()), 'service': 'neural-gold', 'checks': checks}


@app.get('/ready')
async def ready():
    checks = await _service_checks(require_market=True)
    if not all(checks.values()):
        return JSONResponse(
            status_code=503,
            content={
                'ok': False,
                'service': 'neural-gold',
                'checks': checks,
                'detail': 'service_not_ready',
            },
        )
    return {'ok': True, 'service': 'neural-gold', 'checks': checks}


@app.get('/auth/whop/callback', response_class=HTMLResponse)
async def whop_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if error:
        return HTMLResponse(
            '<h2>Whop linking was cancelled.</h2>'
            '<p>Return to Telegram and try again.</p>',
            status_code=400,
        )
    if not code or not state:
        return HTMLResponse('<h2>Invalid Whop callback.</h2>', status_code=400)

    try:
        telegram_id, whop_user_id = await whop.exchange_code(code, state)
        await asyncio.to_thread(database.ensure_user, telegram_id)
        await asyncio.to_thread(database.link_whop_user, telegram_id, whop_user_id)
        if telegram_app is not None:
            await telegram_app.bot.send_message(
                telegram_id,
                '✅ Akun Whop berhasil terhubung. Jika membership Anda ACTIVE '
                'dan Anda sudah menjadi member channel premium, akses Neural Gold '
                'akan tersedia otomatis.',
            )
        return HTMLResponse(
            '<h2>Whop account linked.</h2>'
            '<p>You can return to Telegram and check Status Akses.</p>'
        )
    except ValueError:
        return HTMLResponse(
            '<h2>Whop linking failed.</h2>'
            '<p>Invalid or expired authorization state.</p>',
            status_code=400,
        )
    except Exception:
        log.exception('whop oauth callback failed')
        return HTMLResponse(
            '<h2>Whop linking failed.</h2>'
            '<p>Please return to Telegram and try again.</p>',
            status_code=500,
        )


@app.post('/telegram/webhook')
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    if x_telegram_bot_api_secret_token != TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(403, 'invalid_secret')
    if telegram_app is None:
        raise HTTPException(503, 'telegram_not_ready')

    try:
        body = await request.json()
        update = Update.de_json(body, telegram_app.bot)
        update_id = int(body.get('update_id'))
    except Exception as exc:
        raise HTTPException(400, 'invalid_update') from exc

    claim_token = await asyncio.to_thread(database.claim_telegram_update, update_id)
    if claim_token is None:
        return {'ok': True, 'duplicate': True}

    try:
        await telegram_app.process_update(update)
    except Exception as exc:
        await asyncio.to_thread(database.release_telegram_update, update_id, claim_token)
        log.exception('telegram update processing failed')
        raise HTTPException(500, 'update_processing_failed') from exc

    for attempt in range(1, TELEGRAM_COMPLETION_RETRIES + 1):
        try:
            await asyncio.to_thread(
                database.complete_telegram_update,
                update_id,
                claim_token,
            )
            return {'ok': True, 'duplicate': False}
        except Exception:
            if attempt == TELEGRAM_COMPLETION_RETRIES:
                log.exception(
                    'telegram update completion persistence failed after %s attempts',
                    TELEGRAM_COMPLETION_RETRIES,
                )
                raise HTTPException(500, 'update_completion_failed')
            log.warning(
                'telegram update completion persistence failed; retrying (%s/%s)',
                attempt,
                TELEGRAM_COMPLETION_RETRIES,
                exc_info=True,
            )
            await asyncio.sleep(0.2 * attempt)

    raise HTTPException(500, 'update_completion_failed')


@app.post('/webhooks/whop')
async def whop_webhook(request: Request):
    try:
        data = whop.verify_webhook(await request.body(), request.headers)
    except Exception as exc:
        raise HTTPException(400, 'invalid_webhook') from exc

    try:
        await process_whop(data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return {'ok': True}
