"""NEURAL GOLD v3.2 — Belmo HTTP/Webhook entry point.

Belmo Starter runs one long-lived API service. Telegram sends updates to
POST /telegram/webhook; FastAPI forwards them to python-telegram-bot.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from telegram import Update

import database
from config import BELMO_PUBLIC_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET
from main import build_application, post_init, setup_logging

logger = logging.getLogger("neural_gold.belmo")

telegram_app = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app
    setup_logging()
    database.init_db()
    telegram_app = build_application()
    await telegram_app.initialize()
    await post_init(telegram_app)
    await telegram_app.start()

    if BELMO_PUBLIC_URL:
        webhook_url = f"{BELMO_PUBLIC_URL}/telegram/webhook"
        try:
            await telegram_app.bot.set_webhook(
                url=webhook_url,
                secret_token=TELEGRAM_WEBHOOK_SECRET or None,
                drop_pending_updates=True,
            )
            logger.info("Telegram webhook configured: %s", webhook_url)
        except Exception:
            logger.exception("Telegram webhook registration failed: %s", webhook_url)
    else:
        logger.warning("BELMO_PUBLIC_URL is not set; webhook registration skipped.")

    yield

    if telegram_app:
        try:
            if BELMO_PUBLIC_URL:
                await telegram_app.bot.delete_webhook(drop_pending_updates=False)
        except Exception:
            logger.exception("Failed to delete Telegram webhook")
        await telegram_app.stop()
        await telegram_app.shutdown()


app = FastAPI(title="NEURAL GOLD v3.2", version="3.2.0", lifespan=lifespan)


@app.get("/")
async def root():
    return {"service": "NEURAL GOLD v3.2", "status": "online"}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "neural-gold", "telegram": telegram_app is not None}


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    if TELEGRAM_WEBHOOK_SECRET and x_telegram_bot_api_secret_token != TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    if telegram_app is None:
        raise HTTPException(status_code=503, detail="Bot is starting")

    try:
        data = await request.json()
        update = Update.de_json(data, telegram_app.bot)
        if update is None:
            raise ValueError("Invalid Telegram update")
        await telegram_app.process_update(update)
        return {"ok": True}
    except Exception:
        logger.exception("Telegram webhook processing failed")
        return JSONResponse(status_code=200, content={"ok": False})
