from __future__ import annotations

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


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('📡 Sinyal Terbaru', callback_data='signal'), InlineKeyboardButton('📊 Status Akses', callback_data='status')],
        [InlineKeyboardButton('💳 Pilih Paket', callback_data='plans'), InlineKeyboardButton('ℹ️ Cara Kerja', callback_data='help')],
    ])


def plans_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('7 Hari', callback_data='buy:7'), InlineKeyboardButton('14 Hari', callback_data='buy:14'), InlineKeyboardButton('30 Hari', callback_data='buy:30')],
        [InlineKeyboardButton('⬅️ Menu', callback_data='home')],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    database.ensure_user(update.effective_user.id)
    text = ('<b>NEURAL GOLD</b>\n\n'
            'Premium XAU/USD market intelligence untuk membantu Anda membaca kondisi pasar dengan lebih terstruktur.\n\n'
            '<b>Yang tersedia</b>\n'
            '• Sinyal LONG / SHORT / HOLD\n'
            '• Entry, target & stop saat setup valid\n'
            '• Setup strength berbasis konfirmasi teknikal\n'
            '• Status akses premium\n'
            '• Private Telegram channel\n\n'
            '<i>' + DISCLAIMER + '</i>')
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=main_menu())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = ('<b>CARA KERJA NEURAL GOLD</b>\n\n'
            '1. Data XAU/USD dikumpulkan secara berkala.\n'
            '2. Engine mengevaluasi trend, momentum, volatilitas dan struktur harga.\n'
            '3. Jika konfirmasi belum memadai, sistem memilih <b>HOLD</b>.\n'
            '4. Setup valid menampilkan arah, entry, TP dan stop.\n\n'
            '<b>Arti status</b>\n'
            '🟢 LONG — konfirmasi bullish memenuhi filter\n'
            '🔴 SHORT — konfirmasi bearish memenuhi filter\n'
            '🟡 HOLD — belum ada konfirmasi lengkap\n'
            '⚪ DATA GAP — data belum mencukupi\n\n'
            '<b>Catatan</b>\n'
            'Setup strength bukan probabilitas kemenangan dan tidak menjamin hasil trading.\n\n'
            '<i>' + DISCLAIMER + '</i>')
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=main_menu())

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('<b>PILIH AKSES PREMIUM</b>\n\nPilih durasi yang sesuai kebutuhan Anda:', parse_mode='HTML', reply_markup=plans_menu())

async def make_buy_message(message, telegram_id: int, days: int):
    try:
        url, _ = await whop.create_checkout(telegram_id, days)
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(f'💳 Lanjut ke Pembayaran {days} Hari', url=url)], [InlineKeyboardButton('⬅️ Paket', callback_data='plans')]])
        await message.reply_text(f'<b>Checkout {days} hari siap.</b>\n\nSelesaikan pembayaran melalui halaman Whop. Setelah pembayaran terverifikasi, Anda akan menerima instruksi aktivasi premium.', parse_mode='HTML', reply_markup=keyboard)
    except Exception:
        log.exception('checkout failed')
        await message.reply_text('Checkout belum tersedia. Silakan coba lagi beberapa saat lagi.', reply_markup=plans_menu())

async def buy7(update: Update, context: ContextTypes.DEFAULT_TYPE): await make_buy_message(update.message, update.effective_user.id, 7)
async def buy14(update: Update, context: ContextTypes.DEFAULT_TYPE): await make_buy_message(update.message, update.effective_user.id, 14)
async def buy30(update: Update, context: ContextTypes.DEFAULT_TYPE): await make_buy_message(update.message, update.effective_user.id, 30)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await access.has_access(context.bot, uid):
        await update.message.reply_text('<b>ACCESS: INACTIVE</b>\n\nAkses premium belum aktif atau masa akses telah berakhir. Pilih paket untuk berlangganan.', parse_mode='HTML', reply_markup=plans_menu())
        return
    user = database.get_user(uid)
    expiry = user.subscription_expiry.isoformat() if user else '-'
    await update.message.reply_text(f'<b>ACCESS: ACTIVE</b>\nEXPIRES: {expiry}\n\nAkses premium aktif.', parse_mode='HTML', reply_markup=main_menu())

async def signal_text(uid: int) -> str:
    r = signal_engine.analyze(database.recent_samples())
    signal = r['signal']
    icon = {'LONG':'🟢', 'SHORT':'🔴', 'HOLD':'🟡'}.get(signal, '⚪')
    lines = [f'<b>{icon} NEURAL STRIKES</b>', f'<b>SIGNAL:</b> {signal}', f'<b>SETUP STRENGTH:</b> {r["setup_strength"]}/100', f'<b>TREND:</b> {r["trend"]}']
    if r['rsi'] is not None: lines.append(f'<b>RSI:</b> {r["rsi"]}')
    if r['entry'] is not None: lines.append(f'<b>REFERENCE / ENTRY:</b> {r["entry"]}')
    if r['tp']:
        lines += [f'<b>TP1:</b> {r["tp"][0]}', f'<b>TP2:</b> {r["tp"][1]}', f'<b>TP3:</b> {r["tp"][2]}']
    if r['stop'] is not None: lines.append(f'<b>STOP:</b> {r["stop"]}')
    if r['risk_reward']: lines.append(f'<b>R:R:</b> {r["risk_reward"]}')
    lines += [f'<b>CONDITION:</b> {r["reason"]}', f'<b>DATA:</b> {r["samples"]} samples', '', '<i>Setup strength bukan probabilitas kemenangan.</i>', '<i>' + DISCLAIMER + '</i>']
    return '\n'.join(lines)

async def signal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await access.has_access(context.bot, uid):
        await update.message.reply_text('Premium access diperlukan. Pilih paket untuk melanjutkan.', reply_markup=plans_menu())
        return
    await update.message.reply_text(await signal_text(uid), parse_mode='HTML', reply_markup=main_menu())

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == 'home':
        await q.edit_message_text('<b>NEURAL GOLD</b>\n\nPilih layanan:', parse_mode='HTML', reply_markup=main_menu()); return
    if q.data == 'help':
        await q.edit_message_text('<b>CARA KERJA</b>\n\nData XAU/USD → trend → momentum → volatilitas → struktur → LONG/SHORT atau HOLD. Sistem tidak memaksakan sinyal saat kondisi belum memadai.\n\n<i>Setup strength bukan probabilitas kemenangan.</i>\n\n<i>'+DISCLAIMER+'</i>', parse_mode='HTML', reply_markup=main_menu()); return
    if q.data == 'plans':
        await q.edit_message_text('<b>PILIH AKSES PREMIUM</b>\n\nPilih durasi:', parse_mode='HTML', reply_markup=plans_menu()); return
    if q.data == 'status':
        uid = q.from_user.id
        if await access.has_access(context.bot, uid):
            u = database.get_user(uid); expiry = u.subscription_expiry.isoformat() if u else '-'
            await q.edit_message_text(f'<b>ACCESS: ACTIVE</b>\nEXPIRES: {expiry}', parse_mode='HTML', reply_markup=main_menu())
        else:
            await q.edit_message_text('<b>ACCESS: INACTIVE</b>\n\nPilih paket untuk mengaktifkan akses.', parse_mode='HTML', reply_markup=plans_menu())
        return
    if q.data == 'signal':
        if not await access.has_access(context.bot, q.from_user.id):
            await q.edit_message_text('Premium access diperlukan. Pilih paket untuk melanjutkan.', reply_markup=plans_menu()); return
        await q.edit_message_text(await signal_text(q.from_user.id), parse_mode='HTML', reply_markup=main_menu()); return
    if q.data.startswith('buy:'):
        days = int(q.data.split(':', 1)[1])
        if days not in (7, 14, 30):
            await q.edit_message_text('Paket tidak tersedia.', reply_markup=plans_menu()); return
        await make_buy_message(q.message, q.from_user.id, days)

def build_application() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    for command, handler in [('start', start), ('buy', buy), ('buy7', buy7), ('buy14', buy14), ('buy30', buy30), ('status', status), ('signal', signal_cmd), ('help', help_cmd)]:
        app.add_handler(CommandHandler(command, handler))
    app.add_handler(CallbackQueryHandler(callbacks))
    return app
