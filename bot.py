from __future__ import annotations

import asyncio
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

import access
import database
import signal_engine
import whop
from config import ADMIN_TELEGRAM_ID, TELEGRAM_BOT_TOKEN

log = logging.getLogger('bot')
DISCLAIMER = 'Market information & education only. Not personal financial advice. Trading involves risk; you are responsible for your decisions.'

async def premium_menu(telegram_id: int) -> InlineKeyboardMarkup:
    link_url = await whop.create_link_url(telegram_id)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('⚡ Aktifkan Neural Gold', url=link_url)],
        [InlineKeyboardButton('💳 Berlangganan $49/bulan', url=whop.product_url())],
        [InlineKeyboardButton('⬅️ Menu', callback_data='home')],
    ])

def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton('📡 Sinyal Terbaru', callback_data='signal'), InlineKeyboardButton('📊 Status Akses', callback_data='status')], [InlineKeyboardButton('💳 Premium $49/bulan', callback_data='premium'), InlineKeyboardButton('ℹ️ Cara Kerja', callback_data='help')]])

def main_menu_text() -> str:
    return '<b>NEURAL GOLD</b>\n\nPremium XAU/USD market intelligence.\n\n<b>$49/bulan</b> • recurring melalui Whop.\n\nPilih layanan:'

def _format_signal(r: dict) -> str:
    signal = r['signal']; icon = {'LONG':'🟢', 'SHORT':'🔴', 'HOLD':'🟡'}.get(signal, '⚪')
    lines = [f'<b>{icon} NEURAL STRIKES</b>', f'<b>SIGNAL:</b> {signal}', f'<b>SETUP STRENGTH:</b> {r["setup_strength"]}/100', f'<b>TREND:</b> {r["trend"]}']
    if r.get('rsi') is not None: lines.append(f'<b>RSI:</b> {r["rsi"]}')
    if r.get('entry') is not None: lines.append(f'<b>REFERENCE / ENTRY:</b> {r["entry"]}')
    if r.get('tp'): lines += [f'<b>TP1:</b> {r["tp"][0]}', f'<b>TP2:</b> {r["tp"][1]}', f'<b>TP3:</b> {r["tp"][2]}']
    if r.get('stop') is not None: lines.append(f'<b>STOP:</b> {r["stop"]}')
    if r.get('risk_reward'): lines.append(f'<b>R:R:</b> {r["risk_reward"]}')
    lines += [f'<b>CONDITION:</b> {r["reason"]}', f'<b>DATA:</b> {r["samples"]} samples', '', '<i>Setup strength bukan probabilitas kemenangan.</i>', '<i>' + DISCLAIMER + '</i>']
    return '\n'.join(lines)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.to_thread(database.ensure_user, update.effective_user.id)
    await update.message.reply_text(main_menu_text(), parse_mode='HTML', reply_markup=main_menu())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = ('<b>CARA KERJA NEURAL GOLD</b>\n\n1. Data XAU/USD dikumpulkan secara berkala.\n2. Engine mengevaluasi trend, momentum, volatilitas dan struktur harga.\n3. Engine menghasilkan kandidat setup.\n4. Untuk Premium Channel, <b>human approval</b> menjadi gate sebelum sinyal dipublikasikan.\n5. Bot Telegram menyediakan signal secara mandiri setelah akses premium aktif.\n\n'
            '<b>Arti status</b>\n🟢 LONG — signal bullish\n🔴 SHORT — signal bearish\n🟡 HOLD — kondisi belum mendukung setup\n⚪ DATA GAP — data belum mencukupi\n\n'
            '<b>Catatan</b>\nSetup strength bukan probabilitas kemenangan dan tidak menjamin hasil trading.\n\n<i>' + DISCLAIMER + '</i>')
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=main_menu())

async def premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text('<b>NEURAL GOLD PREMIUM</b>\n\nHarga: <b>$49/bulan</b>\nPembayaran dan entitlement dikelola oleh Whop.\n\n<b>Aktivasi satu kali:</b>\n1. Selesaikan langganan $49/bulan di Whop.\n2. Tekan <b>Aktifkan Neural Gold</b> dan selesaikan sign-in Whop satu kali.\n3. Setelah membership Whop ACTIVE dan Anda menjadi member channel premium, akses bot aktif otomatis.\n\nSetelah terhubung, Anda tidak perlu login Whop lagi untuk menggunakan bot.', parse_mode='HTML', reply_markup=await premium_menu(update.effective_user.id))
    except Exception:
        log.exception('premium menu failed')
        await update.message.reply_text('Menu premium belum tersedia. Silakan coba lagi beberapa saat lagi.')

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await access.has_access(context.bot, uid):
        await update.message.reply_text('<b>ACCESS: INACTIVE</b>\n\nSelesaikan aktivasi Whop satu kali, pastikan membership ACTIVE, dan pastikan Anda menjadi member channel premium.', parse_mode='HTML', reply_markup=await premium_menu(uid)); return
    m = await asyncio.to_thread(database.get_membership_for_telegram, uid)
    expiry = m.renewal_period_end.isoformat() if m and m.renewal_period_end else '-'
    await update.message.reply_text(f'<b>ACCESS: ACTIVE</b>\nWHOP MEMBERSHIP: ACTIVE\nRENEWAL PERIOD END: {expiry}\n\nAkses bot premium aktif.', parse_mode='HTML', reply_markup=main_menu())

async def signal_text(uid: int) -> str:
    approved = await asyncio.to_thread(database.latest_approved_signal)
    if not approved:
        return '<b>🟡 NEURAL STRIKES</b>\n\n<b>SIGNAL:</b> HOLD\n<b>CONDITION:</b> AWAITING_HUMAN_APPROVAL\n\nBelum ada signal channel yang disetujui.\n\n<i>' + DISCLAIMER + '</i>'
    return _format_signal(approved)

async def signal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await access.has_access(context.bot, update.effective_user.id):
        await update.message.reply_text('Premium access diperlukan. Aktifkan Neural Gold dan pastikan membership premium aktif.', reply_markup=await premium_menu(update.effective_user.id)); return
    await update.message.reply_text(await signal_text(update.effective_user.id), parse_mode='HTML', reply_markup=main_menu())

async def approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_TELEGRAM_ID:
        await update.message.reply_text('Perintah tidak tersedia.')
        return
    samples = await asyncio.to_thread(database.recent_samples)
    candidate = signal_engine.analyze(samples)
    await asyncio.to_thread(database.save_approved_signal, candidate, update.effective_user.id)
    await update.message.reply_text('<b>SETUP APPROVED</b>\n\n' + _format_signal(candidate), parse_mode='HTML')

async def link_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = await whop.create_link_url(update.effective_user.id)
    await update.message.reply_text('<b>AKTIVASI NEURAL GOLD</b>\n\nSelesaikan sign-in Whop satu kali. Setelah akun Whop terhubung, status membership akan menentukan akses bot secara otomatis.', parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⚡ Aktifkan Neural Gold', url=url)], [InlineKeyboardButton('⬅️ Menu', callback_data='home')]]))

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.data == 'home': await q.edit_message_text(main_menu_text(), parse_mode='HTML', reply_markup=main_menu()); return
    if q.data == 'help': await q.edit_message_text('<b>CARA KERJA</b>\n\nData XAU/USD → trend → momentum → volatilitas → struktur → signal.\n\n<b>Premium Channel:</b> signal harus melalui human approval sebelum dipublikasikan.\n<b>Bot:</b> signal tersedia secara mandiri setelah akses premium aktif.\n\n<i>Setup strength bukan probabilitas kemenangan.</i>\n\n<i>'+DISCLAIMER+'</i>', parse_mode='HTML', reply_markup=main_menu()); return
    if q.data == 'premium':
        await q.edit_message_text('<b>NEURAL GOLD PREMIUM</b>\n\nHarga: <b>$49/bulan</b>\nPembayaran dan entitlement dikelola oleh Whop.\n\nAktivasi satu kali: selesaikan langganan di Whop, lalu tekan <b>Aktifkan Neural Gold</b>. Setelah membership ACTIVE dan Anda menjadi member channel premium, akses bot aktif otomatis.', parse_mode='HTML', reply_markup=await premium_menu(q.from_user.id)); return
    if q.data == 'status':
        uid = q.from_user.id
        if await access.has_access(context.bot, uid):
            m = await asyncio.to_thread(database.get_membership_for_telegram, uid); expiry = m.renewal_period_end.isoformat() if m and m.renewal_period_end else '-'
            await q.edit_message_text(f'<b>ACCESS: ACTIVE</b>\nWHOP MEMBERSHIP: ACTIVE\nRENEWAL PERIOD END: {expiry}\n\nAkses bot premium aktif.', parse_mode='HTML', reply_markup=main_menu())
        else: await q.edit_message_text('<b>ACCESS: INACTIVE</b>\n\nSelesaikan aktivasi Whop satu kali, pastikan membership ACTIVE, dan pastikan Anda menjadi member channel premium.', parse_mode='HTML', reply_markup=await premium_menu(uid))
        return
    if q.data == 'signal':
        if not await access.has_access(context.bot, q.from_user.id): await q.edit_message_text('Premium access diperlukan. Aktifkan Neural Gold dan pastikan membership premium aktif.', reply_markup=await premium_menu(q.from_user.id)); return
        await q.edit_message_text(await signal_text(q.from_user.id), parse_mode='HTML', reply_markup=main_menu()); return

def build_application() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    for command, handler in [('start', start), ('premium', premium), ('buy', premium), ('link', link_cmd), ('status', status), ('signal', signal_cmd), ('help', help_cmd), ('approve', approve_cmd)]: app.add_handler(CommandHandler(command, handler))
    app.add_handler(CallbackQueryHandler(callbacks)); return app
