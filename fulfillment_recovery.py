"""Fulfillment recovery worker: stale-claim recovery and notification delivery."""
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
        "<b>⚠ FULFILLMENT FAILURE</b>\n━━━━━━━━━━━━━━━━━━━━\n"
        f"PAYMENT: <code>{item.get('payment_id')}</code>\n"
        f"ORDER: <code>{item.get('order_id')}</code>\n"
        f"USER: <code>{tg if tg is not None else '?'}</code>\n"
        f"PLAN: <b>{item.get('duration_days', '?')} DAYS</b>\n"
        f"ATTEMPTS: <b>{item.get('attempts', '?')}</b>\n"
        "STATUS: FAILED — automatic recovery exhausted.\n"
        f">> Manual review required. /reconcile <code>{item.get('payment_id')}</code>"
    )


async def recovery_job(telegram_app) -> dict:
    """Recover stale claims and deliver every pending customer notification."""
    report = recover_stale_fulfillments(
        stale_minutes=STALE_FULFILLMENT_MINUTES,
        max_attempts=MAX_FULFILLMENT_ATTEMPTS,
    )
    if telegram_app is not None:
        notified = set()
        for item in report["recovered"]:
            try:
                await notify_customer(
                    telegram_app.bot,
                    int(item["telegram_id"]),
                    int(item["duration_days"]),
                    item["order_id"],
                )
                notified.add(item["order_id"])
            except Exception:
                logger.exception("Recovered fulfillment notification failed payment=%s", item.get("payment_id"))
        for order in whop_storage.list_unnotified_orders(min_age_seconds=90):
            if order["id"] in notified:
                continue
            try:
                await notify_customer(
                    telegram_app.bot,
                    int(order["telegram_id"]),
                    int(order["duration_days"]),
                    order["id"],
                )
            except Exception:
                logger.exception("Pending fulfillment notification failed order=%s", order["id"])
    if report["exhausted"] and telegram_app is not None and ADMIN_TELEGRAM_ID:
        for item in report["exhausted"]:
            try:
                await telegram_app.bot.send_message(
                    chat_id=ADMIN_TELEGRAM_ID,
                    text=build_admin_alert(item),
                    parse_mode="HTML",
                )
            except Exception:
                logger.exception("Failed to send fulfillment alert to admin")
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
    logger.info("Fulfillment recovery worker scheduled every %ds.", _INTERVAL_SECONDS)
