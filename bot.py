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
DISCLAIMER = 'Market information & education only. Not personal financial advice. Trading involves risk; you are responsible for your decisions.'

async def activation_menu(telegram_id: int) -> InlineKeyboardMarkup:
    link_url = await whop.create_link_url(telegram_id)
    return InlineKeyboardMarkup([[InlineKeyboardButton('🔗 Hubungkan Akun Whop', url=link_url)], [InlineKeyboardButton('⬅️ Menu', callback_data='home')]])

def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('📡 Sinyal Terbaru', callback_data='signal'), InlineKeyboardButton('📊 Status Akses', callback_data='status')],
        [InlineKeyboardButton('🔗 Hubungkan Akun Whop', callback_data='premium'), InlineKeyboardButton('ℹ️ Cara Kerja', callback_data='help')],
    ])

def main_menu_text() -> str:
    return '<b>NEURAL GOLD</b>\n\nPremium XAU/USD market intelligence.\n\n<b>$49/bulan</b> • recurring melalui Whop.\n\nPilih layanan:'

def _format_signal(r: dict) -> str:
    signal = r['signal']; icon = {'LONG':'🟢', 'SHORT':'🔴', 'HOLD':'🟡'}.get(signal, '⚪')
    lines = [f'<b>{icon} NEURAL STRIKES</b>', f'<b>SIGNAL:</b> {signal}', f'<b>SETUP STRENGTH:</b> {r["setup_strength"]}/100', f'<b>TREND:</b> {r["trend"]}']
    if r.get('rsi') is not None: lines.append(f'<b>RSI:</b> {r["rsi"]}')
    if r.get('entry') is not None: lines.append(f'<b>REFERENCE / ENTRY:</b> {r["entry"]}')
    if r.get('tp'): lines += [f'<b>TP1:</b> {r["tp"][0]}', f'<b>TP2:</b> {r["tp"][1]}', f'<b>TP3:</b> {r["tp"][2]}']
    if r.get('stop') is not None: lines.append(f'<b>STOP LOSS:</b> {r["stop"]}')
    if r.get('risk_reward'): lines.append(f'<b>R:R:</b> {r["risk_reward"]}')
    lines += [f'<b>CONDITION:</b> {r["reason"]}', f'<b>DATA:</b> {r["samples"]} samples', '', '<i>Setup strength bukan probabilitas kemenangan.</i>', '<i>' + DISCLAIMER + '</i>']
    return '\n'.join(lines)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.to_thread(database.ensure_user, update.effective_user.id)
    await update.message.reply_text(main_menu_text(), parse_mode='HTML', reply_markup=main_menu())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = ('<b>CARA KERJA NEURAL GOLD</b>\n\n1. Data XAU/USD dikumpulkan otomatis.\n2. Engine mengevaluasi trend, momentum, volatilitas dan struktur harga.\n3. Engine menghasilkan signal.\n4. Signal LONG/SHORT yang memenuhi rule dipublikasikan otomatis ke Premium Channel.\n5. Bot Telegram menyediakan signal secara mandiri setelah akses premium aktif.\n\n<b>Arti status</b>\n🟢 LONG — signal bullish\n🔴 SHORT — signal bearish\n🟡 HOLD — kondisi belum mendukung setup\n⚪ DATA GAP — data belum mencukupi\n\n<b>Catatan</b>\nSetup strength bukan probabilitas kemenangan dan tidak menjamin hasil trading.\n\n<i>' + DISCLAIMER + '</i>')
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=main_menu())

async def premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text('<b>AKTIVASI NEURAL GOLD</b>\n\nPembayaran dan entitlement dikelola oleh Whop. Bot tidak memproses pembayaran.\n\n<b>Aktivasi / penghubungan akun:</b>\n1. Selesaikan langganan Neural Gold di Whop.\n2. Tekan <b>Hubungkan Akun Whop</b> dan selesaikan sign-in Whop satu kali.\n3. Pastikan membership Whop ACTIVE dan Anda sudah menjadi member channel premium.\n4. Sistem memeriksa kedua status tersebut untuk akses premium.\n\nSetelah akun terhubung, Anda tidak perlu login Whop lagi untuk menggunakan bot.', parse_mode='HTML', reply_markup=await activation_menu(update.effective_user.id))
    except Exception:
        log.exception('activation menu failed'); await update.message.reply_text('Menu aktivasi belum tersedia. Silakan coba lagi beberapa saat lagi.')

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await access.has_access(context.bot, uid):
        await update.message.reply_text('<b>ACCESS: INACTIVE</b>\n\nPastikan membership Whop ACTIVE, akun Whop sudah terhubung, dan Anda menjadi member channel premium.', parse_mode='HTML', reply_markup=await activation_menu(uid)); return
    m = await asyncio.to_thread(database.get_membership_for_telegram, uid); expiry = m.renewal_period_end.isoformat() if m and m.renewal_period_end else '-'
    await update.message.reply_text(f'<b>ACCESS: ACTIVE</b>\nWHOP MEMBERSHIP: ACTIVE\nRENEWAL PERIOD END: {expiry}\n\nAkses bot premium aktif.', parse_mode='HTML', reply_markup=main_menu())

async def signal_text() -> str:
    samples = await asyncio.to_thread(database.recent_samples)
    return _format_signal(signal_engine.analyze(samples))

async def signal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await access.has_access(context.bot, update.effective_user.id):
        await update.message.reply_text('Premium access diperlukan. Hubungkan akun Whop dan pastikan membership serta channel premium aktif.', reply_markup=await activation_menu(update.effective_user.id)); return
    await update.message.reply_text(await signal_text(), parse_mode='HTML', reply_markup=main_menu())

async def link_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('<b>AKTIVASI NEURAL GOLD</b>\n\nHubungkan akun Whop ke Telegram satu kali. Membership Whop tetap menjadi sumber entitlement.', parse_mode='HTML', reply_markup=await activation_menu(update.effective_user.id))

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.data == 'home': await q.edit_message_text(main_menu_text(), parse_mode='HTML', reply_markup=main_menu()); return
    if q.data == 'help':
        await q.edit_message_text('<b>CARA KERJA</b>\n\nData XAU/USD → signal engine.\n\n<b>Premium Channel:</b> LONG/SHORT yang memenuhi rule → <b>publikasi otomatis</b>.\n<b>Bot:</b> signal tersedia secara mandiri setelah akses premium aktif.\n\n<i>Setup strength bukan probabilitas kemenangan.</i>\n\n<i>'+DISCLAIMER+'</i>', parse_mode='HTML', reply_markup=main_menu()); return
    if q.data == 'premium':
        await q.edit_message_text('<b>AKTIVASI NEURAL GOLD</b>\n\nSelesaikan pembelian di Whop terlebih dahulu, lalu hubungkan akun Whop melalui tombol di bawah. Bot tidak menjual paket dan tidak menangani pembayaran.', parse_mode='HTML', reply_markup=await activation_menu(q.from_user.id)); return
    if q.data == 'status':
        uid = q.from_user.id
        if await access.has_access(context.bot, uid):
            m = await asyncio.to_thread(database.get_membership_for_telegram, uid); expiry = m.renewal_period_end.isoformat() if m and m.renewal_period_end else '-'
            await q.edit_message_text(f'<b>ACCESS: ACTIVE</b>\nWHOP MEMBERSHIP: ACTIVE\nRENEWAL PERIOD END: {expiry}\n\nAkses bot premium aktif.', parse_mode='HTML', reply_markup=main_menu())
        else: await q.edit_message_text('<b>ACCESS: INACTIVE</b>\n\nPastikan membership Whop ACTIVE, akun Whop sudah terhubung, dan Anda menjadi member channel premium.', parse_mode='HTML', reply_markup=await activation_menu(uid))
        return
    if q.data == 'signal':
        if not await access.has_access(context.bot, q.from_user.id): await q.edit_message_text('Premium access diperlukan. Hubungkan akun Whop dan pastikan membership serta channel premium aktif.', reply_markup=await activation_menu(q.from_user.id)); return
        await q.edit_message_text(await signal_text(), parse_mode='HTML', reply_markup=main_menu()); return

def build_application() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    for command, handler in [('start', start), ('premium', premium), ('link', link_cmd), ('status', status), ('signal', signal_cmd), ('help', help_cmd)]: app.add_handler(CommandHandler(command, handler))
    app.add_handler(CallbackQueryHandler(callbacks)); return app
