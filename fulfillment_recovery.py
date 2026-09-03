"""Fulfillment recovery worker: periodic stale-claim recovery + admin alerting."""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import whop_storage
from config import ADMIN_TELEGRAM_ID
from whop_webhook_phase2 import MAX_FULFILLMENT_ATTEMPTS, STALE_FULFILLMENT_MINUTES, notify_customer, recover_stale_fulfillments

logger = logging.getLogger("neural_gold.fulfillment_recovery")
_INTERVAL_SECONDS = 60


def build_admin_alert(item: dict) -> str:
    tg = item.get("telegram_id")
    return (
        "<b>⚠ FULFILLMENT FAILURE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"PAYMENT: <code>{item.get('payment_id')}</code>\n"
        f"ORDER: <code>{item.get('order_id')}</code>\n"
        f"USER: <code>{tg if tg is not None else '?'}</code>\n"
        f"PLAN: <b>{item.get('duration_days', '?')} DAYS</b>\n"
        f"ATTEMPTS: <b>{item.get('attempts', '?')}</b>\n"
        "STATUS: FAILED — automatic recovery exhausted.\n"
        f">> Manual review required. /reconcile <code>{item.get('payment_id')}</code>"
    )


async def recovery_job(telegram_app) -> dict:
    """Recover stale claims and deliver recovered access to the customer."""
    report = recover_stale_fulfillments(stale_minutes=STALE_FULFILLMENT_MINUTES, max_attempts=MAX_FULFILLMENT_ATTEMPTS)
    if report["recovered"] and telegram_app is not None:
        for item in report["recovered"]:
            try:
                claim = whop_storage.get_fulfillment(item["payment_id"])
                order = whop_storage.get_order(item["order_id"])
                if not claim or not order:
                    continue
                # Recovery now returns the raw token so customer delivery is complete.
                raw_token = item.get("raw_token")
                if raw_token:
                    await notify_customer(
                        telegram_app.bot,
                        int(item["telegram_id"]),
                        raw_token,
                        int(item["duration_days"]),
                        item["order_id"],
                    )
            except Exception:
                logger.exception("Recovered fulfillment notification failed payment=%s", item.get("payment_id"))
    if report["exhausted"] and ADMIN_TELEGRAM_ID:
        bot = telegram_app.bot
        for item in report["exhausted"]:
            try:
                await bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text=build_admin_alert(item), parse_mode="HTML")
            except Exception:
                logger.exception("Failed to send fulfillment alert to admin")
    if report["recovered"]:
        logger.info("Recovery worker recovered %d fulfillment(s).", len(report["recovered"]))
    return report


def schedule(telegram_app) -> None:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        recovery_job,
        "interval",
        seconds=_INTERVAL_SECONDS,
        args=[telegram_app],
        max_instances=1,
        coalesce=True,
        id="fulfillment_recovery",
    )
    scheduler.start()
    logger.info("Fulfillment recovery worker scheduled (every %ds, stale>%dmin, max_attempts=%d).",
                _INTERVAL_SECONDS, STALE_FULFILLMENT_MINUTES, MAX_FULFILLMENT_ATTEMPTS)
