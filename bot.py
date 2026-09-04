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

async def premium_menu(telegram_id: int) -> InlineKeyboardMarkup:
    link_url = await whop.create_link_url(telegram_id)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🔗 Hubungkan Akun Whop', url=link_url)],
        [InlineKeyboardButton('💳 Berlangganan $49/bulan', url=whop.product_url())],
        [InlineKeyboardButton('⬅️ Menu', callback_data='home')],
    ])

def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton('📡 Sinyal Terbaru', callback_data='signal'), InlineKeyboardButton('📊 Status Akses', callback_data='status')], [InlineKeyboardButton('💳 Premium $49/bulan', callback_data='premium'), InlineKeyboardButton('ℹ️ Cara Kerja', callback_data='help')]])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.to_thread(database.ensure_user, update.effective_user.id)
    text = ('<b>NEURAL GOLD</b>\n\nPremium XAU/USD market intelligence untuk membantu Anda membaca kondisi pasar dengan lebih terstruktur.\n\n'
            '<b>Yang tersedia</b>\n• Sinyal LONG / SHORT / HOLD\n• Entry, target & stop saat setup valid\n• Setup strength berbasis konfirmasi teknikal\n• Status akses premium\n• Private Telegram channel\n\n'
            '<b>Premium:</b> $49/bulan, recurring melalui Whop.\n\n<i>' + DISCLAIMER + '</i>')
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=main_menu())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = ('<b>CARA KERJA NEURAL GOLD</b>\n\n1. Data XAU/USD dikumpulkan secara berkala.\n2. Engine mengevaluasi trend, momentum, volatilitas dan struktur harga.\n3. Jika konfirmasi belum memadai, sistem memilih <b>HOLD</b>.\n4. Setup valid menampilkan arah, entry, TP dan stop.\n\n'
            '<b>Arti status</b>\n🟢 LONG — konfirmasi bullish memenuhi filter\n🔴 SHORT — konfirmasi bearish memenuhi filter\n🟡 HOLD — belum ada konfirmasi lengkap\n⚪ DATA GAP — data belum mencukupi\n\n<b>Catatan</b>\nSetup strength bukan probabilitas kemenangan dan tidak menjamin hasil trading.\n\n<i>' + DISCLAIMER + '</i>')
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=main_menu())

async def premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text('<b>NEURAL GOLD PREMIUM</b>\n\nHarga: <b>$49/bulan</b>\nPembayaran dan entitlement dikelola oleh Whop.\n\n<b>Langkah:</b>\n1. Hubungkan akun Whop ke Telegram Anda.\n2. Selesaikan langganan $49/bulan di Whop.\n3. Kembali ke Telegram dan buka Status Akses.\n\nSetelah membership Whop ACTIVE dan Anda menjadi member channel premium, akses diberikan otomatis.', parse_mode='HTML', reply_markup=await premium_menu(update.effective_user.id))
    except Exception:
        log.exception('premium menu failed')
        await update.message.reply_text('Menu premium belum tersedia. Silakan coba lagi beberapa saat lagi.')

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await access.has_access(context.bot, uid):
        await update.message.reply_text('<b>ACCESS: INACTIVE</b>\n\nAkun Whop belum terhubung, membership belum ACTIVE, atau Anda belum menjadi member channel premium.', parse_mode='HTML', reply_markup=await premium_menu(uid)); return
    m = await asyncio.to_thread(database.get_membership_for_telegram, uid)
    expiry = m.renewal_period_end.isoformat() if m and m.renewal_period_end else '-'
    await update.message.reply_text(f'<b>ACCESS: ACTIVE</b>\nWHOP MEMBERSHIP: ACTIVE\nRENEWAL PERIOD END: {expiry}\n\nAkses premium aktif.', parse_mode='HTML', reply_markup=main_menu())

async def signal_text(uid: int) -> str:
    samples = await asyncio.to_thread(database.recent_samples)
    r = signal_engine.analyze(samples)
    signal = r['signal']; icon = {'LONG':'🟢', 'SHORT':'🔴', 'HOLD':'🟡'}.get(signal, '⚪')
    lines = [f'<b>{icon} NEURAL STRIKES</b>', f'<b>SIGNAL:</b> {signal}', f'<b>SETUP STRENGTH:</b> {r["setup_strength"]}/100', f'<b>TREND:</b> {r["trend"]}']
    if r['rsi'] is not None: lines.append(f'<b>RSI:</b> {r["rsi"]}')
    if r['entry'] is not None: lines.append(f'<b>REFERENCE / ENTRY:</b> {r["entry"]}')
    if r['tp']: lines += [f'<b>TP1:</b> {r["tp"][0]}', f'<b>TP2:</b> {r["tp"][1]}', f'<b>TP3:</b> {r["tp"][2]}']
    if r['stop'] is not None: lines.append(f'<b>STOP:</b> {r["stop"]}')
    if r['risk_reward']: lines.append(f'<b>R:R:</b> {r["risk_reward"]}')
    lines += [f'<b>CONDITION:</b> {r["reason"]}', f'<b>DATA:</b> {r["samples"]} samples', '', '<i>Setup strength bukan probabilitas kemenangan.</i>', '<i>' + DISCLAIMER + '</i>']
    return '\n'.join(lines)

async def signal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await access.has_access(context.bot, update.effective_user.id):
        await update.message.reply_text('Premium access diperlukan. Hubungkan akun Whop dan aktifkan membership premium.', reply_markup=await premium_menu(update.effective_user.id)); return
    await update.message.reply_text(await signal_text(update.effective_user.id), parse_mode='HTML', reply_markup=main_menu())

async def link_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = await whop.create_link_url(update.effective_user.id)
    await update.message.reply_text('<b>HUBUNGKAN AKUN WHOP</b>\n\nBuka tombol di bawah dan selesaikan sign-in Whop. Setelah berhasil, akun Whop akan ditautkan ke Telegram ini.', parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔗 Hubungkan Akun Whop', url=url)], [InlineKeyboardButton('⬅️ Menu', callback_data='home')]]))

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.data == 'home': await q.edit_message_text('<b>NEURAL GOLD</b>\n\nPilih layanan:', parse_mode='HTML', reply_markup=main_menu()); return
    if q.data == 'help': await q.edit_message_text('<b>CARA KERJA</b>\n\nData XAU/USD → trend → momentum → volatilitas → struktur → LONG/SHORT atau HOLD. Sistem tidak memaksakan sinyal saat kondisi belum memadai.\n\n<i>Setup strength bukan probabilitas kemenangan.</i>\n\n<i>'+DISCLAIMER+'</i>', parse_mode='HTML', reply_markup=main_menu()); return
    if q.data == 'premium':
        await q.edit_message_text('<b>NEURAL GOLD PREMIUM</b>\n\nHarga: <b>$49/bulan</b>\nPembayaran dan entitlement dikelola oleh Whop.\n\nHubungkan akun Whop terlebih dahulu, lalu selesaikan langganan.', parse_mode='HTML', reply_markup=await premium_menu(q.from_user.id)); return
    if q.data == 'status':
        uid = q.from_user.id
        if await access.has_access(context.bot, uid):
            m = await asyncio.to_thread(database.get_membership_for_telegram, uid); expiry = m.renewal_period_end.isoformat() if m and m.renewal_period_end else '-'
            await q.edit_message_text(f'<b>ACCESS: ACTIVE</b>\nWHOP MEMBERSHIP: ACTIVE\nRENEWAL PERIOD END: {expiry}', parse_mode='HTML', reply_markup=main_menu())
        else: await q.edit_message_text('<b>ACCESS: INACTIVE</b>\n\nAkun Whop belum terhubung, membership belum ACTIVE, atau Anda belum menjadi member channel premium.', parse_mode='HTML', reply_markup=await premium_menu(uid))
        return
    if q.data == 'signal':
        if not await access.has_access(context.bot, q.from_user.id): await q.edit_message_text('Premium access diperlukan. Hubungkan akun Whop dan aktifkan membership premium.', reply_markup=await premium_menu(q.from_user.id)); return
        await q.edit_message_text(await signal_text(q.from_user.id), parse_mode='HTML', reply_markup=main_menu()); return

def build_application() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    for command, handler in [('start', start), ('premium', premium), ('buy', premium), ('link', link_cmd), ('status', status), ('signal', signal_cmd), ('help', help_cmd)]: app.add_handler(CommandHandler(command, handler))
    app.add_handler(CallbackQueryHandler(callbacks)); return app
