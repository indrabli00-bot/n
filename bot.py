from __future__ import annotations

import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

import access
import database
import signal_engine
import whop
from config import TELEGRAM_BOT_TOKEN

log = logging.getLogger('bot')
DISCLAIMER = (
    'Market information & education only. Not personal financial advice. '
    'Trading involves risk; you are responsible for your decisions.'
)

HELP_TEXT = (
    '<b>CARA KERJA NEURAL GOLD</b>\n\n'
    '1. Data XAU/USD dikumpulkan otomatis.\n'
    '2. Engine mengevaluasi trend, momentum, volatilitas dan struktur harga.\n'
    '3. Engine menghasilkan signal.\n'
    '4. Signal LONG/SHORT yang memenuhi rule dipublikasikan otomatis ke Premium Channel.\n'
    '5. Bot Telegram menyediakan signal secara mandiri setelah akses premium aktif.\n\n'
    '<b>Arti status</b>\n'
    '🟢 LONG — signal bullish\n'
    '🔴 SHORT — signal bearish\n'
    '🟡 HOLD — kondisi belum mendukung setup\n'
    '⚪ DATA GAP — data belum mencukupi\n\n'
    '<b>Catatan</b>\n'
    'Setup strength bukan probabilitas kemenangan dan tidak menjamin hasil trading.\n\n'
    f'<i>{DISCLAIMER}</i>'
)

ACTIVATION_TEXT = (
    '<b>AKTIVASI NEURAL GOLD</b>\n\n'
    'Pembayaran dan entitlement dikelola oleh Whop. Bot tidak memproses pembayaran.\n\n'
    '<b>Aktivasi / penghubungan akun:</b>\n'
    '1. Selesaikan langganan Neural Gold di Whop.\n'
    '2. Tekan <b>Hubungkan Akun Whop</b> dan selesaikan sign-in Whop satu kali.\n'
    '3. Pastikan membership Whop ACTIVE dan Anda sudah menjadi member channel premium.\n'
    '4. Sistem memeriksa kedua status tersebut untuk akses premium.\n\n'
    'Setelah akun terhubung, Anda tidak perlu login Whop lagi untuk menggunakan bot.'
)

ACCESS_INACTIVE_TEXT = (
    '<b>ACCESS: INACTIVE</b>\n\n'
    'Pastikan membership Whop ACTIVE, akun Whop sudah terhubung, dan Anda '
    'menjadi member channel premium.'
)

PREMIUM_REQUIRED_TEXT = (
    'Premium access diperlukan. Hubungkan akun Whop dan pastikan membership '
    'serta channel premium aktif.'
)


def access_active_text(expiry: str) -> str:
    return (
        '<b>ACCESS: ACTIVE</b>\n'
        '<b>WHOP MEMBERSHIP:</b> ACTIVE\n'
        f'<b>RENEWAL PERIOD END:</b> {expiry}\n\n'
        'Akses bot premium aktif.'
    )


async def activation_menu(telegram_id: int) -> InlineKeyboardMarkup:
    link_url = await whop.create_link_url(telegram_id)
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton('🔗 Hubungkan Akun Whop', url=link_url)],
            [InlineKeyboardButton('⬅️ Menu', callback_data='home')],
        ]
    )


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton('📡 Sinyal Terbaru', callback_data='signal'),
                InlineKeyboardButton('📊 Status Akses', callback_data='status'),
            ],
            [
                InlineKeyboardButton('🔗 Hubungkan Akun Whop', callback_data='premium'),
                InlineKeyboardButton('ℹ️ Cara Kerja', callback_data='help'),
            ],
        ]
    )


def main_menu_text() -> str:
    return (
        '<b>NEURAL GOLD</b>\n\n'
        'Premium XAU/USD market intelligence.\n\n'
        '<b>$49/bulan</b> • recurring melalui Whop.\n\n'
        'Pilih layanan:'
    )


def _format_signal(result: dict) -> str:
    signal = result.get('signal', 'HOLD')
    icon = {'LONG': '🟢', 'SHORT': '🔴', 'HOLD': '🟡'}.get(signal, '⚪')
    lines = [
        f'<b>{icon} NEURAL STRIKES</b>',
        f'<b>SIGNAL:</b> {signal}',
        f'<b>SETUP STRENGTH:</b> {result.get("setup_strength", 0)}/100',
        f'<b>TREND:</b> {result.get("trend", "NEUTRAL")}',
    ]
    if result.get('rsi') is not None:
        lines.append(f'<b>RSI:</b> {result["rsi"]}')
    if result.get('entry') is not None:
        lines.append(f'<b>REFERENCE / ENTRY:</b> {result["entry"]}')

    targets = result.get('tp') or []
    for index, target in enumerate(targets[:3], start=1):
        lines.append(f'<b>TP{index}:</b> {target}')
    if result.get('stop') is not None:
        lines.append(f'<b>STOP LOSS:</b> {result["stop"]}')
    if result.get('risk_reward'):
        lines.append(f'<b>R:R:</b> {result["risk_reward"]}')

    lines.extend(
        [
            f'<b>CONDITION:</b> {result.get("reason", "UNKNOWN")}',
            f'<b>DATA:</b> {result.get("samples", 0)} samples',
            '',
            '<i>Setup strength bukan probabilitas kemenangan.</i>',
            f'<i>{DISCLAIMER}</i>',
        ]
    )
    return '\n'.join(lines)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.to_thread(database.ensure_user, update.effective_user.id)
    await update.message.reply_text(
        main_menu_text(), parse_mode='HTML', reply_markup=main_menu()
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        HELP_TEXT, parse_mode='HTML', reply_markup=main_menu()
    )


async def _send_activation(target, telegram_id: int, *, edit: bool = False) -> None:
    markup = await activation_menu(telegram_id)
    if edit:
        await target.edit_message_text(
            ACTIVATION_TEXT, parse_mode='HTML', reply_markup=markup
        )
    else:
        await target.reply_text(
            ACTIVATION_TEXT, parse_mode='HTML', reply_markup=markup
        )


async def premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await _send_activation(update.message, update.effective_user.id)
    except Exception:
        log.exception('activation menu failed')
        await update.message.reply_text(
            'Menu aktivasi belum tersedia. Silakan coba lagi beberapa saat lagi.'
        )


async def _status_text(uid: int, bot) -> tuple[str, InlineKeyboardMarkup]:
    if not await access.has_access(bot, uid):
        return ACCESS_INACTIVE_TEXT, await activation_menu(uid)

    membership = await asyncio.to_thread(database.get_membership_for_telegram, uid)
    expiry = (
        membership.renewal_period_end.isoformat()
        if membership and membership.renewal_period_end
        else '-'
    )
    return access_active_text(expiry), main_menu()


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, markup = await _status_text(update.effective_user.id, context.bot)
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=markup)


async def signal_text() -> str:
    samples = await asyncio.to_thread(database.recent_samples)
    return _format_signal(signal_engine.analyze(samples))


async def _send_signal(target, uid: int, bot) -> None:
    if not await access.has_access(bot, uid):
        if hasattr(target, 'edit_message_text'):
            await target.edit_message_text(
                PREMIUM_REQUIRED_TEXT,
                reply_markup=await activation_menu(uid),
            )
        else:
            await target.reply_text(
                PREMIUM_REQUIRED_TEXT,
                reply_markup=await activation_menu(uid),
            )
        return

    text = await signal_text()
    if hasattr(target, 'edit_message_text'):
        await target.edit_message_text(text, parse_mode='HTML', reply_markup=main_menu())
    else:
        await target.reply_text(text, parse_mode='HTML', reply_markup=main_menu())


async def signal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_signal(update.message, update.effective_user.id, context.bot)


async def link_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await _send_activation(update.message, update.effective_user.id)
    except Exception:
        log.exception('activation link failed')
        await update.message.reply_text(
            'Menu aktivasi belum tersedia. Silakan coba lagi beberapa saat lagi.'
        )


async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'home':
        await query.edit_message_text(
            main_menu_text(), parse_mode='HTML', reply_markup=main_menu()
        )
        return
    if query.data == 'help':
        await query.edit_message_text(
            HELP_TEXT, parse_mode='HTML', reply_markup=main_menu()
        )
        return
    if query.data == 'premium':
        try:
            await _send_activation(query, query.from_user.id, edit=True)
        except Exception:
            log.exception('callback activation failed')
            await query.edit_message_text(
                'Menu aktivasi belum tersedia. Silakan coba lagi beberapa saat lagi.',
                reply_markup=main_menu(),
            )
        return
    if query.data == 'status':
        text, markup = await _status_text(query.from_user.id, context.bot)
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=markup)
        return
    if query.data == 'signal':
        await _send_signal(query, query.from_user.id, context.bot)


def build_application() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    handlers = {
        'start': start,
        'premium': premium,
        'link': link_cmd,
        'status': status,
        'signal': signal_cmd,
        'help': help_cmd,
    }
    for command, handler in handlers.items():
        app.add_handler(CommandHandler(command, handler))
    app.add_handler(CallbackQueryHandler(callbacks))
    return app
