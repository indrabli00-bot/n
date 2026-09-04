from __future__ import annotations
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
import access, database, signal_engine, whop
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
            '• Status akses premium\n'
            '• Akses melalui Telegram private channel\n\n'
            '<i>' + DISCLAIMER + '</i>')
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=main_menu())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = ('<b>CARA KERJA NEURAL GOLD</b>\n\n'
            '1. Data XAU/USD dikumpulkan secara berkala.\n'
            '2. Engine mengevaluasi trend, momentum dan struktur harga.\n'
            '3. Jika konfirmasi belum memadai, sistem memilih <b>HOLD</b> — bukan memaksakan trade.\n'
            '4. Setup valid menampilkan arah, entry, TP dan stop.\n\n'
            '<b>Arti status</b>\n'
            '🟢 LONG — bias bullish terkonfirmasi\n'
            '🔴 SHORT — bias bearish terkonfirmasi\n'
            '🟡 HOLD — belum ada konfirmasi yang cukup\n'
            '⚪ DATA GAP — data belum mencukupi\n\n'
            '<i>' + DISCLAIMER + '</i>')
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=main_menu())

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('<b>PILIH AKSES PREMIUM</b>\n\nPilih durasi yang sesuai kebutuhan Anda:', parse_mode='HTML', reply_markup=plans_menu())

async def make_buy_message(message, telegram_id: int, days: int):
    try:
        url, _ = await whop.create_checkout(telegram_id, days)
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(f'💳 Bayar {days} Hari', url=url)], [InlineKeyboardButton('⬅️ Paket', callback_data='plans')]])
        await message.reply_text(f'<b>Checkout {days} hari siap.</b>\n\nSelesaikan pembayaran melalui halaman Whop. Setelah pembayaran terverifikasi, akses premium akan diaktifkan.', parse_mode='HTML', reply_markup=keyboard)
    except Exception:
        log.exception('checkout failed')
        await message.reply_text('Checkout belum tersedia. Silakan coba lagi beberapa saat lagi.', reply_markup=plans_menu())

async def buy7(update: Update, context: ContextTypes.DEFAULT_TYPE): await make_buy_message(update.message, update.effective_user.id, 7)
async def buy14(update: Update, context: ContextTypes.DEFAULT_TYPE): await make_buy_message(update.message, update.effective_user.id, 14)
async def buy30(update: Update, context: ContextTypes.DEFAULT_TYPE): await make_buy_message(update.message, update.effective_user.id, 30)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await access.has_access(context.bot, uid):
        await update.message.reply_text('<b>ACCESS: INACTIVE</b>\n\nAkses premium belum aktif atau masa akses telah berakhir. Pilih <b>Pilih Paket</b> untuk berlangganan.', parse_mode='HTML', reply_markup=plans_menu())
        return
    user = database.get_user(uid)
    expiry = user.subscription_expiry.isoformat() if user else '-'
    await update.message.reply_text(f'<b>ACCESS: ACTIVE</b>\nEXPIRES: {expiry}\n\nAnda memiliki akses premium aktif.', parse_mode='HTML', reply_markup=main_menu())

async def signal_text(uid: int) -> str:
    r = signal_engine.analyze(database.recent_samples())
    signal = r['signal']
    icon = {'LONG':'🟢', 'SHORT':'🔴', 'HOLD':'🟡'}.get(signal, '⚪')
    lines = [f'<b>{icon} NEURAL STRIKES</b>', f'<b>SIGNAL:</b> {signal}', f'<b>SETUP STRENGTH:</b> {r["confidence"]}/100']
    if r['entry'] is not None: lines.append(f'<b>ENTRY:</b> {r["entry"]}')
    if r['tp']:
        lines += [f'<b>TP1:</b> {r["tp"][0]}', f'<b>TP2:</b> {r["tp"][1]}', f'<b>TP3:</b> {r["tp"][2]}']
    if r['stop'] is not None: lines.append(f'<b>STOP:</b> {r["stop"]}')
    lines += [f'<b>CONDITION:</b> {r["reason"]}', f'<b>DATA:</b> {r["samples"]} samples', '', '<i>' + DISCLAIMER + '</i>']
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
        await q.edit_message_text('<b>CARA KERJA</b>\n\nData XAU/USD → evaluasi trend & struktur → konfirmasi → LONG/SHORT atau HOLD. Sistem tidak memaksakan sinyal saat kondisi belum memadai.\n\n<i>'+DISCLAIMER+'</i>', parse_mode='HTML', reply_markup=main_menu()); return
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
        await make_buy_message(q.message, q.from_user.id, days)

def build_application() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    for command, handler in [('start', start), ('buy', buy), ('buy7', buy7), ('buy14', buy14), ('buy30', buy30), ('status', status), ('signal', signal_cmd), ('help', help_cmd)]:
        app.add_handler(CommandHandler(command, handler))
    app.add_handler(CallbackQueryHandler(callbacks))
    return app
