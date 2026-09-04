from __future__ import annotations
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import access, database, signal_engine, whop
from config import TELEGRAM_BOT_TOKEN

log = logging.getLogger('bot')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    database.ensure_user(update.effective_user.id)
    await update.message.reply_text('NEURAL GOLD\n\nPremium XAU/USD market intelligence.\n\n/buy — paket akses\n/status — status akses\n/signal — sinyal terbaru')

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('PILIH AKSES:\n/buy7 — 7 hari\n/buy14 — 14 hari\n/buy30 — 30 hari')

async def make_buy(update: Update, days: int):
    try:
        url, _ = await whop.create_checkout(update.effective_user.id, days)
        await update.message.reply_text(f'Checkout {days} hari:\n{url}')
    except Exception:
        log.exception('checkout failed')
        await update.message.reply_text('Checkout belum tersedia. Silakan coba lagi.')

async def buy7(u, c): await make_buy(u, 7)
async def buy14(u, c): await make_buy(u, 14)
async def buy30(u, c): await make_buy(u, 30)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await access.has_access(context.bot, uid):
        await update.message.reply_text('ACCESS: INACTIVE\nGunakan /buy untuk berlangganan.')
        return
    user = database.get_user(uid)
    expiry = user.subscription_expiry.isoformat() if user else '-'
    await update.message.reply_text(f'ACCESS: ACTIVE\nEXPIRES: {expiry}')

async def signal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await access.has_access(context.bot, uid):
        await update.message.reply_text('Premium access diperlukan. Gunakan /buy.')
        return
    r = signal_engine.analyze(database.recent_samples())
    lines = [f"NEURAL STRIKES", f"SIGNAL: {r['signal']}"]
    if r['entry'] is not None: lines.append(f"ENTRY: {r['entry']}")
    if r['tp']: lines += [f"TP1: {r['tp'][0]}", f"TP2: {r['tp'][1]}", f"TP3: {r['tp'][2]}"]
    if r['stop'] is not None: lines.append(f"STOP: {r['stop']}")
    lines += [f"REASON: {r['reason']}", f"CONFIDENCE: {r['confidence']}%", f"SAMPLES: {r['samples']}", '', 'Market information only. Not financial advice.']
    await update.message.reply_text('\n'.join(lines))

def build_application() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    for command, handler in [('start', start), ('buy', buy), ('buy7', buy7), ('buy14', buy14), ('buy30', buy30), ('status', status), ('signal', signal_cmd)]:
        app.add_handler(CommandHandler(command, handler))
    return app
