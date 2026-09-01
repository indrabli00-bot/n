"""
main.py — Premium Telegram UI for the XAU/USD Neural Signal Engine.

The bot is intentionally command-light: customers navigate the product with
inline buttons instead of memorising commands. Commands remain available for
administration and token activation.
"""
import asyncio
import html
import logging
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import Application, ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
import api_handler
import auth
import database
import terminal_style as ts
import whop_storage
from i18n import LANGUAGES, detect_language, language_buttons, t
from terminal_style import render_header, render_terminal_box
from config import ADMIN_TELEGRAM_ID, LOG_FILE, LOG_FORMAT, LOG_LEVEL, NEURAL_VERSION, SIGNAL_VALIDITY_MINUTES, TELEGRAM_BOT_TOKEN
logger = logging.getLogger(__name__)
DIVIDER = '─' * 40
ALPHA_TERMS = {'rsi': 'TEMPORAL MOMENTUM RESONANCE', 'macd': 'DUAL-PHASE CONVERGENCE MANIFOLD', 'ema': 'SYNAPTIC TREND ALIGNMENT', 'stoch': 'PROBABILISTIC FLUX', 'atr': 'VOLATILITY VARIANCE', 'bollinger': 'QUANTUM ENVELOPE POSITION'}
SHORT_DESCRIPTION = 'NEURAL GOLD v3.2 — PREMIUM XAU/USD TERMINAL INTELLIGENCE.'
BOT_DESCRIPTION = 'NEURAL GOLD v3.2 — PREMIUM XAU/USD MARKET INTELLIGENCE\n\n━━━━━━━━━━━━━━━━━━━━\n\n[ SYSTEM ]: XAU/USD INTELLIGENCE TERMINAL ONLINE.\n\nLive pricing · Neural signal reads · Market structure · Private operator access.\n\n>> PRESS /start TO INITIALIZE.'

def _lang(update: Update) -> str:
    user = update.effective_user
    if not user:
        return 'en'
    return database.get_user_language(user.id)

def _lang_text(update: Update, key: str) -> str:
    return t(_lang(update), key)

def _esc(value: object) -> str:
    return html.escape(str(value))

def _money(value: float) -> str:
    return f'{value:,.2f}'

def _format_timestamp(value: str) -> str:
    """Render feed timestamps as compact UTC clock time for the terminal UI."""
    try:
        raw = value.replace('Z', '+00:00')
        return datetime.fromisoformat(raw).strftime('%H:%M:%S')
    except Exception:
        return _esc(value[-8:] if len(value) >= 8 else value)

def _safe_user_name(user) -> str:
    return _esc(user.first_name or 'OPERATOR')

def _is_active(update: Update) -> bool:
    user = update.effective_user
    return bool(user and auth.verify_token(user.id)[0])


def _persistent_nav(update: Update) -> list[InlineKeyboardButton]:
    return list(ts.render_persistent_nav(_lang(update)).inline_keyboard[0])


def _keyboard(update: Update, rows=None) -> InlineKeyboardMarkup:
    keyboard = list(rows or [])
    keyboard.append(_persistent_nav(update))
    return InlineKeyboardMarkup(keyboard)


def _module_button(label: str, callback: str, locked: bool = False) -> InlineKeyboardButton:
    return InlineKeyboardButton(f"🔒 {label}" if locked else label, callback_data=callback)


def home_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    if _is_active(update):
        rows = [[InlineKeyboardButton("MARKET PULSE", callback_data="screen:price"), InlineKeyboardButton("NEURAL STRIKES", callback_data="screen:signal")], [InlineKeyboardButton("STRUCTURE MAP", callback_data="screen:analysis")]]
    else:
        rows = [[_module_button("MARKET PULSE", "screen:price", True), _module_button("NEURAL STRIKES", "screen:signal", True)], [_module_button("STRUCTURE MAP", "screen:analysis", True)], [InlineKeyboardButton(f"💎 {t(lang, 'activate_premium')}", callback_data="screen:activate")]]
    return _keyboard(update, rows)


def _module_nav(update: Update, screen: str) -> list[list[InlineKeyboardButton]]:
    return [[InlineKeyboardButton(t(_lang(update), "refresh"), callback_data=f"refresh:{screen}")], [InlineKeyboardButton("MARKET PULSE", callback_data="screen:price"), InlineKeyboardButton("NEURAL STRIKES", callback_data="screen:signal")], [InlineKeyboardButton("STRUCTURE MAP", callback_data="screen:analysis")]]


def price_keyboard(update: Update) -> InlineKeyboardMarkup:
    rows = _module_nav(update, "price") if _is_active(update) else [[InlineKeyboardButton(f"💎 {t(_lang(update), 'activate_premium')}", callback_data="screen:activate")]]
    return _keyboard(update, rows)


def signal_keyboard(update: Update) -> InlineKeyboardMarkup:
    rows = _module_nav(update, "signal") if _is_active(update) else [[InlineKeyboardButton(f"💎 {t(_lang(update), 'activate_premium')}", callback_data="screen:activate")]]
    return _keyboard(update, rows)


def analysis_keyboard(update: Update) -> InlineKeyboardMarkup:
    rows = _module_nav(update, "analysis") if _is_active(update) else [[InlineKeyboardButton(f"💎 {t(_lang(update), 'activate_premium')}", callback_data="screen:activate")]]
    return _keyboard(update, rows)


def account_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    if _is_active(update):
        rows = [[InlineKeyboardButton(f"🔄 {t(lang, 'renew')}", callback_data="screen:renew")], [InlineKeyboardButton(f"📊 {t(lang, 'history')}", callback_data="screen:history")]]
    else:
        rows = [[InlineKeyboardButton(f"💎 {t(lang, 'activate_premium')}", callback_data="screen:activate")]]
    return _keyboard(update, rows)


def access_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    import phase2_bot
    tid = update.effective_user.id
    rows = [[InlineKeyboardButton(f"🟢 {t(lang, 'days7')}", url=phase2_bot.checkout_link(tid, 7)), InlineKeyboardButton(f"🟡 {t(lang, 'days14')}", url=phase2_bot.checkout_link(tid, 14))], [InlineKeyboardButton(f"🔵 {t(lang, 'days30')}", url=phase2_bot.checkout_link(tid, 30))]]
    return _keyboard(update, rows)


def settings_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    rows = [[InlineKeyboardButton(t(lang, "interface"), callback_data="noop")], [InlineKeyboardButton(t(lang, "timezone"), callback_data="noop")], [InlineKeyboardButton(t(lang, "data_mode"), callback_data="noop")]]
    if not _is_active(update):
        rows.append([InlineKeyboardButton(f"💎 {t(lang, 'activate_premium')}", callback_data="screen:activate")])
    return _keyboard(update, rows)


def language_keyboard(update: Update) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(label, callback_data=data)] for label, data in language_buttons()]
    if not _is_active(update):
        rows.append([InlineKeyboardButton(f"💎 {t(_lang(update), 'activate_premium')}", callback_data="screen:activate")])
    return _keyboard(update, rows)


def support_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    rows = []
    if ADMIN_TELEGRAM_ID:
        rows.append([InlineKeyboardButton(t(lang, "contact"), url=f"tg://user?id={ADMIN_TELEGRAM_ID}")])
    if not _is_active(update):
        rows.append([InlineKeyboardButton(f"💎 {t(lang, 'activate_premium')}", callback_data="screen:activate")])
    return _keyboard(update, rows)


def _screen(update: Update, terminal: str, context_text: str | None = None) -> str:
    lang = _lang(update)
    body = render_terminal_box(terminal, max_width=70)
    text = f"{render_header(update.effective_user, lang)}\n\n<pre>{body}</pre>"
    if context_text:
        text += f"\n\n{context_text}"
    return text


def _error_screen(update: Update) -> str:
    lang = _lang(update)
    return _screen(update, "[ ERROR ]\nPermintaan timeout.\nServer tidak merespons.", f">> {t(lang, 'try_again')}")


async def render_home(update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool = True) -> None:
    if update.effective_user is None:
        return
    active = _is_active(update)
    terminal = "\n".join(["[ SYSTEM ]: INITIALIZING...", "[ STATUS ]: SYNCING GLOBAL BULLION RESERVES...", "[ ACCESS ]: GRANTED // WELCOME OPERATOR" if active else "[ ACCESS ]: PENDING // CLEARANCE REQUIRED"])
    await _present(update, _screen(update, terminal, f">> {t(_lang(update), 'select_module')}"), home_keyboard(update), edit=edit)


async def render_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return
    if not _is_active(update):
        await render_locked(update, "price")
        return
    try:
        await _answer_loading(update)
        data = await asyncio.wait_for(api_handler.get_cached_or_fresh_price(user.id), timeout=10.0)
        bid = float(data["bid"]); ask = float(data["ask"]); mid = (bid + ask) / 2
        terminal = "\n".join(["[ MARKET PULSE ]", f"PRICE  : {_money(mid)}", f"BID    : {_money(bid)}", f"ASK    : {_money(ask)}", f"HIGH   : {_money(float(data['high']))}", f"LOW    : {_money(float(data['low']))}", f"SOURCE : {_esc(data.get('source', '—'))}"])
        await _present(update, _screen(update, terminal, f">> {t(_lang(update), 'live_feed')} // XAU/USD"), price_keyboard(update))
    except Exception:
        logger.exception("Premium price screen failed")
        await _present(update, _error_screen(update), price_keyboard(update))


async def render_signal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return
    if not _is_active(update):
        await render_locked(update, "signal")
        return
    try:
        await _answer_loading(update)
        data = await asyncio.wait_for(api_handler.get_cached_or_fresh_price(user.id), timeout=10.0)
        indicators = api_handler._simulate_technical_indicators(float(data["bid"]), float(data.get("change_percent", 0)))
        signal = api_handler._determine_signal(float(data["bid"]), indicators)
        terminal = "\n".join(["[ NEURAL STRIKES ]", f"SIGNAL : {signal['direction']}", f"ENTRY  : {_money(signal['entry_low'])} - {_money(signal['entry_high'])}", f"TP1    : {_money(signal['tp1']) if signal['tp1'] else '—'}", f"TP2    : {_money(signal['tp2']) if signal['tp2'] else '—'}", f"TP3    : {_money(signal['tp3']) if signal['tp3'] else '—'}", f"STOP   : {_money(signal['sl']) if signal['sl'] else '—'}"])
        await _present(update, _screen(update, terminal, f">> {t(_lang(update), 'neural_signal')} // XAU/USD"), signal_keyboard(update))
    except Exception:
        logger.exception("Signal screen failed")
        await _present(update, _error_screen(update), signal_keyboard(update))


async def render_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return
    if not _is_active(update):
        await render_locked(update, "analysis")
        return
    try:
        await _answer_loading(update)
        data = await asyncio.wait_for(api_handler.get_cached_or_fresh_price(user.id), timeout=10.0)
        indicators = api_handler._simulate_technical_indicators(float(data["bid"]), float(data.get("change_percent", 0)))
        terminal = "\n".join(["[ STRUCTURE MAP ]", f"TREND  : {_esc(str(indicators.get('ema_trend', 'NEUTRAL')).upper())}", f"RSI    : {indicators.get('rsi', '—')}", f"MACD   : {indicators.get('macd_hist', '—')}", f"EMA    : {indicators.get('ema', '—')}", f"ATR    : {indicators.get('atr', '—')}"])
        await _present(update, _screen(update, terminal, f">> {t(_lang(update), 'analysis_title')} // XAU/USD"), analysis_keyboard(update))
    except Exception:
        logger.exception("Analysis screen failed")
        await _present(update, _error_screen(update), analysis_keyboard(update))


async def render_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return
    db_user = database.get_user_by_telegram_id(user.id)
    active = _is_active(update)
    if active and db_user:
        expiry = database.normalize_datetime_utc(db_user.subscription_expiry)
        expiry_text = expiry.strftime("%d %b %Y • %H:%M UTC") if expiry else "—"
        days_left = max(0, (expiry - datetime.now(timezone.utc)).days) if expiry else 0
        terminal = "\n".join(["[ OPERATOR HUB ]", f"TELEGRAM_ID : {user.id}", "CLEARANCE   : PREMIUM AKTIF", f"KEDALUWARSA : {expiry_text}", f"SISA HARI   : {days_left} hari tersisa"])
        context_text = f">> {t(_lang(update), 'account_status')} // {t(_lang(update), 'active')}"
    else:
        terminal = "\n".join(["[ OPERATOR HUB ]", f"TELEGRAM_ID : {user.id}", "CLEARANCE   : NONAKTIF", "STATUS      : Belum ada langganan aktif"])
        context_text = f">> {t(_lang(update), 'account_status')} // {t(_lang(update), 'inactive')}"
    await _present(update, _screen(update, terminal, context_text), account_keyboard(update))


async def render_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await render_activate(update, context)


async def render_activate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _lang(update)
    terminal = "\n".join(["[ ACCESS & PACKAGE ]", f"🟢 {t(lang, 'days7')}", f"🟡 {t(lang, 'days14')}", f"🔵 {t(lang, 'days30')}"])
    await _present(update, _screen(update, terminal, f">> {t(lang, 'select_plan')} // {t(lang, 'activate_premium')}"), access_keyboard(update))


async def render_renew(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await render_activate(update, context)


async def render_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return
    lang = _lang(update)
    active = _is_active(update)
    rows = ["[ OPERATOR HUB ]"]
    try:
        orders = whop_storage.recent_orders_for(user.id, 5)
    except Exception:
        orders = []
    if orders:
        for order in orders:
            order_id = _esc(str(order.get("id", "—"))[:20])
            status = _esc(str(order.get("status", "—")).upper())
            days = order.get("duration_days", "—")
            rows.append(f"TRANSACTION : <code>{order_id}</code>")
            rows.append(f"STATUS      : {status}")
            rows.append(f"DURATION    : {days} days")
            rows.append("")
    else:
        rows.append("—")
    keyboard_rows = []
    if not active:
        keyboard_rows.append([InlineKeyboardButton(f"💎 {t(lang, 'activate_premium')}", callback_data="screen:activate")])
    await _present(
        update,
        _screen(update, "\n".join(rows).rstrip(), f">> {t(lang, 'history')} // {t(lang, 'account')}"),
        _keyboard(update, keyboard_rows),
    )

async def render_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _lang(update)
    terminal = "\n".join(["[ SYSTEM SYNC ]", t(lang, "settings_title"), f"• {t(lang, 'access')}", f"• {t(lang, 'settings')}", f"• {t(lang, 'language')}", f"• {t(lang, 'history')}", f"• {t(lang, 'support')}"])
    rows = [[InlineKeyboardButton(t(lang, "access"), callback_data="screen:activate"), InlineKeyboardButton(t(lang, "settings"), callback_data="screen:settings")], [InlineKeyboardButton(t(lang, "language"), callback_data="settings:language"), InlineKeyboardButton(t(lang, "support"), callback_data="screen:help")], [InlineKeyboardButton(t(lang, "history"), callback_data="screen:history")]]
    if not _is_active(update):
        rows.append([InlineKeyboardButton(f"💎 {t(lang, 'activate_premium')}", callback_data="screen:activate")])
    await _present(update, _screen(update, terminal, f">> {t(lang, 'menu')} // {t(lang, 'settings')}"), _keyboard(update, rows))


async def render_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _lang(update)
    await _present(update, _screen(update, t(lang, "help_body"), f">> {t(lang, 'support')} // FAQ"), support_keyboard(update))


async def render_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _lang(update)
    terminal = "\n".join(["[ SYSTEM SYNC ]", t(lang, "settings_title"), f"{t(lang, 'interface')} : ON", f"{t(lang, 'timezone')} : UTC+7", f"{t(lang, 'language_value')} : {lang.upper()}"])
    await _present(update, _screen(update, terminal, f">> {t(lang, 'settings')} // {t(lang, 'language')}"), settings_keyboard(update))


async def render_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _lang(update)
    terminal = "\n".join(["[ SUPPORT & HELP ]", t(lang, "support_title"), t(lang, "support_need")])
    await _present(update, _screen(update, terminal, f">> {t(lang, 'support')}"), support_keyboard(update))


async def render_locked(update: Update, module: str) -> None:
    lang = _lang(update)
    labels = {"price": "MARKET PULSE", "signal": "NEURAL STRIKES", "analysis": "STRUCTURE MAP"}
    label = labels.get(module, module.upper())
    terminal = "\n".join(["[ ACCESS DENIED ]", "MODUL TERKUNCI", f"{t(lang, 'activate_required')}", f"{label}."])
    await _present(update, _screen(update, terminal, f">> {t(lang, 'access_required')} // {t(lang, 'activate_premium')}"), _keyboard(update, [[InlineKeyboardButton(f"💎 {t(lang, 'activate_premium')}", callback_data="screen:activate")]]))


async def _answer_loading(update: Update, text: str | None = None) -> None:
    query = update.callback_query
    if query:
        try:
            await query.answer(t(_lang(update), "loading"), show_alert=False)
        except Exception:
            pass


async def _present(update: Update, text: str, keyboard: InlineKeyboardMarkup, edit: bool = True) -> None:
    query = update.callback_query
    if query and edit:
        try:
            await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=keyboard)
            return
        except BadRequest as exc:
            if "not modified" in str(exc).lower():
                return
        except Exception as exc:
            logger.debug("Could not edit callback message: %s", exc)
    try:
        if query and query.message:
            await query.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
            return
    except Exception as exc:
        logger.debug("Callback reply fallback failed: %s", exc)
    if update.message:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return
    try:
        existing = database.get_user_by_telegram_id(user.id)
        if existing is None:
            database.create_user(user.id, user.username, user.first_name, detect_language(user.language_code))
            logger.info('New user registered: %d (%s)', user.id, user.username)
    except Exception as exc:
        logger.exception('Failed to register user during /start: %s', exc)
    active, _ = auth.verify_token(user.id)
    await render_home(update, context, edit=False)

async def activate_token_for_user(update: Update, context: ContextTypes.DEFAULT_TYPE, raw_token: str) -> None:
    """Activate a single-use token and return the user to the premium dashboard."""
    user = update.effective_user
    if user is None:
        return
    existing = database.get_user_by_telegram_id(user.id)
    if existing is None:
        database.create_user(user.id, user.username, user.first_name)
    import hashlib
    from sqlalchemy import select
    from database import TokenPool, _get_session
    token_hash = hashlib.sha256(raw_token.strip().encode('utf-8')).hexdigest()
    session = _get_session()
    try:
        entry = session.scalar(select(TokenPool).where(TokenPool.token_hash == token_hash, TokenPool.is_used == False))
        duration = entry.duration_days if entry else 30
    finally:
        session.close()
    success = database.activate_user_token(user.id, raw_token, duration)
    if success:
        db_user = database.get_user_by_telegram_id(user.id)
        expiry = database.normalize_datetime_utc(db_user.subscription_expiry) if db_user else None
        expiry_text = expiry.strftime('%d %b %Y • %H:%M UTC') if expiry else '—'
        text = f'<b>[ ACCESS ]: TOKEN ACCEPTED // CLEARANCE GRANTED</b>\n{DIVIDER}\n\n[ SYSTEM ]: {t(_lang(update), 'activation_active')}\n\nExpires  <code>{expiry_text}</code>\nPackage  <b>{duration} days</b>\n\n>> [ CORE ]: {t(_lang(update), 'modules_unlocked')}'
        await _present(update, text, home_keyboard(update), edit=False)
    else:
        await _present(update, '<b>[ ERROR ]: TOKEN_REJECTED</b>\n\n[ FAULT ]: INVALID_OR_ALREADY_BURNED\nThe token is invalid or has already been used.\n\n>> Tap <b>ACCESS &amp; PLANS</b> to try again.', access_keyboard(update), edit=False)

async def token_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Accept a token after the user taps ACTIVATE TOKEN."""
    if not context.user_data.get('awaiting_token'):
        return
    context.user_data['awaiting_token'] = False
    raw_token = (update.message.text or '').strip()
    lang = _lang(update)
    if not raw_token:
        await update.message.reply_text(f'[ ERROR ]: EMPTY_INPUT\n>> {t(lang, 'send_token')}', reply_markup=access_keyboard(update))
        return
    try:
        await activate_token_for_user(update, context, raw_token)
    except Exception as exc:
        logger.exception('Interactive token activation failed: %s', exc)
        await update.message.reply_text(f'[ FAULT ]: ACTIVATION_LINK_TIMEOUT // RETRYING...\n{t(lang, 'activation_unavailable')}', parse_mode='HTML', reply_markup=access_keyboard(update))

async def token_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fallback activation command for users who prefer commands."""
    if not context.args:
        await update.message.reply_text(f'<b>[ KEYGEN ]: ACTIVATE ACCESS</b>\n\n>> {t(_lang(update), 'enter_activation')}', parse_mode='HTML', reply_markup=access_keyboard(update))
        return
    try:
        await activate_token_for_user(update, context, ' '.join(context.args).strip())
    except Exception as exc:
        logger.exception('Error during /token: %s', exc)
        await update.message.reply_text(f'[ FAULT ]: ACTIVATION_LINK_TIMEOUT // RETRYING...\n{t(_lang(update), 'activation_unavailable')}', parse_mode='HTML')

@auth.require_admin
async def addtoken_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    if len(args) == 0:
        generated, days = (secrets.token_urlsafe(24), 30)
    elif len(args) == 1 and args[0].isdigit():
        generated, days = (secrets.token_urlsafe(24), int(args[0]))
    else:
        generated = args[0].strip()
        days = int(args[1]) if len(args) >= 2 and args[1].isdigit() else 30
    try:
        if database.add_token_to_pool(generated, duration_days=days):
            await update.message.reply_text(f'<b>[ KEYGEN ]: TOKEN_MINTED</b>\n\n<code>{generated}</code>\n\nVALIDITY: <b>{days} days</b>\n>> Deliver via secure channel only. Single-use.', parse_mode='HTML')
        else:
            await update.message.reply_text('<b>[ ERROR ]: TOKEN_CREATION_FAILED</b>', parse_mode='HTML')
    except Exception:
        logger.exception('Error in /addtoken')
        await update.message.reply_text('[ FAULT ]: INTERNAL_ERROR // CHECK LOGS', parse_mode='HTML')

@auth.require_admin
async def listusers_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        users = database.list_all_users()
        if not users:
            await update.message.reply_text('[ ERROR ]: NO_OPERATORS_IN_REGISTRY')
            return
        lines = [f'<b>[ DATABASE ]: OPERATOR REGISTRY • {len(users)}</b>', DIVIDER]
        for u in users:
            icon = '🟢' if u['is_active'] else '○'
            exp = u['subscription_expiry'][:16] if u['subscription_expiry'] else '—'
            lines.append(f'{icon} <code>{u['telegram_id']}</code> @{_esc(u['username'] or '-')} • {exp}')
        await update.message.reply_text('\n'.join(lines), parse_mode='HTML')
    except Exception:
        logger.exception('Error in /listusers')
        await update.message.reply_text('[ ERROR ]: DB_READ_FAILED // CONTACT SYSADMIN', parse_mode='HTML')

@auth.require_admin
async def fulfillment_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        q = whop_storage.fulfillment_queue()
    except Exception:
        logger.exception('fulfillment_command failed')
        await update.message.reply_text('<b>[ ERROR ]: OPS QUEUE UNAVAILABLE</b>', parse_mode='HTML')
        return
    counts = q['counts']
    lines = ['<b>[ OPS ]: FULFILLMENT QUEUE</b>', f'FULFILLED {counts.get('fulfilled', 0)} · PROCESSING {counts.get('processing', 0)} · FAILED {counts.get('failed', 0)}', DIVIDER]
    rows = q['rows']
    if not rows:
        lines.append('>> [ CORE ]: EXCEPTION QUEUE EMPTY. ALL PAYMENTS AUTOMATIC.')
    for r in rows:
        tg = r.get('telegram_id') or '?'
        lines.append(f'⚠ <code>{_esc(str(r['payment_id'])[:20])}</code> · {_esc(str(r['status']).upper())} · attempts {r['attempts']} · user <code>{tg}</code> · {r.get('duration_days') or '?'}d')
    lines.append('>> /reconcile &lt;payment_id&gt; to force re-check.')
    await update.message.reply_text('\n'.join(lines), parse_mode='HTML')

@auth.require_admin
async def reconcile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text('>> USAGE: <code>/reconcile PAYMENT_ID</code>', parse_mode='HTML')
        return
    payment_id = context.args[0].strip()
    import whop_webhook_phase2
    try:
        result = await whop_webhook_phase2.reconcile_payment_full(payment_id)
    except Exception as exc:
        logger.exception('reconcile_command failed')
        result = {'ok': False, 'reason': str(exc)[:120]}
    if result.get('ok'):
        expiry_line = f'\nEXPIRY: <code>{_esc(result.get('expiry'))}</code>' if result.get('expiry') else ''
        await update.message.reply_text(f'<b>[ OPS ]: RECONCILE OK</b>\nSTATUS: <b>{_esc(result.get('status'))}</b>\nUSER: <code>{result.get('telegram_id')}</code>{expiry_line}', parse_mode='HTML')
    else:
        await update.message.reply_text(f'<b>[ OPS ]: RECONCILE FAILED</b>\n[ ERROR ]: {_esc(result.get('reason'))}', parse_mode='HTML')

@auth.require_admin
async def user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or not context.args[0].strip().lstrip('-').isdigit():
        await update.message.reply_text('>> USAGE: <code>/user TELEGRAM_ID</code>', parse_mode='HTML')
        return
    tid = int(context.args[0].strip())
    user = database.get_user_by_telegram_id(tid)
    if user is None:
        await update.message.reply_text(f'<b>[ FILE ]: USER <code>{tid}</code></b>\n[ ERROR ]: NOT_FOUND', parse_mode='HTML')
        return
    expiry = database.normalize_datetime_utc(user.subscription_expiry)
    expiry_text = expiry.strftime('%d %b %Y • %H:%M UTC') if expiry else 'Not activated'
    lines = ['<b>[ FILE ]: OPERATOR DOSSIER</b>', f'TELEGRAM_ID: <code>{tid}</code>', f'USERNAME: <code>@{_esc(user.username or 'N/A')}</code>', f'STATUS: <b>{('🟢 ACTIVE' if user.is_active else '○ INACTIVE')}</b>', f'EXPIRY: <code>{expiry_text}</code>', DIVIDER]
    orders = whop_storage.recent_orders_for(tid, 3)
    if orders:
        lines.append('<b>RECENT ORDERS:</b>')
        for o in orders:
            lines.append(f'• <code>{_esc(str(o['id'])[:18])}</code> · {_esc(o['status'])} · {o['duration_days']}d')
        latest_payment = orders[0].get('payment_id')
        latest = whop_storage.get_fulfillment(latest_payment) if latest_payment else None
        if latest:
            lines.append(f'FULFILLMENT: {_esc(str(latest['status']).upper())} (attempts {latest['attempts']})')
    else:
        lines.append('RECENT ORDERS: —')
    await update.message.reply_text('\n'.join(lines), parse_mode='HTML')

@auth.require_admin
async def revoke_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or not context.args[0].strip().lstrip('-').isdigit():
        await update.message.reply_text('>> USAGE: <code>/revoke TELEGRAM_ID</code>', parse_mode='HTML')
        return
    target_id = int(context.args[0].strip())
    try:
        success = database.revoke_user(target_id)
        await update.message.reply_text(f'[ ACCESS ]: {('REVOKED' if success else 'TARGET_NOT_FOUND')} // <code>{target_id}</code>', parse_mode='HTML')
    except Exception:
        logger.exception('Error in /revoke')
        await update.message.reply_text('[ FAULT ]: INTERNAL_ERROR // CHECK LOGS', parse_mode='HTML')

async def paid_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Notify the configured admin that a customer reports a completed Whop payment."""
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    try:
        await query.answer('[ LOG ]: PAYMENT NOTICE TRANSMITTED', show_alert=False)
    except Exception:
        pass
    username = f'@{user.username}' if user.username else '(no username)'
    text = f'<b>[ INCOMING ]: PAYMENT NOTICE</b>\n{DIVIDER}\nCUSTOMER: <b>{_esc(user.first_name or 'Trader')}</b>\nUSERNAME: <code>{_esc(username)}</code>\nTELEGRAM_ID: <code>{user.id}</code>\n\n>> Customer reports that a Whop payment was completed.\n>> Verify the Whop order manually, then issue the matching token via /addtoken.'
    recent = whop_storage.recent_orders_for(user.id, 3)
    if recent:
        text += '\n\n<b>RECENT ORDERS (THIS USER):</b>\n' + '\n'.join((f'• <code>{_esc(str(o['id'])[:20])}</code> · {_esc(o['status'])} · {o['duration_days']}d' for o in recent))
    if ADMIN_TELEGRAM_ID:
        try:
            await context.bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text=text, parse_mode='HTML')
        except Exception:
            logger.exception('Failed to send payment notice to admin')
    await query.message.reply_text(f'<b>[ LOG ]: PAYMENT NOTICE REGISTERED</b>\n\n{t(_lang(update), 'payment_notice_registered')}\n\n{t(_lang(update), 'activate_note')}', parse_mode='HTML', reply_markup=access_keyboard(update))

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    data = query.data or ""
    if data == "noop":
        await query.answer(show_alert=True)
        return
    if data == "paid:menu":
        await paid_confirmation(update, context)
        return
    if data == "nav:home":
        await render_home(update, context)
        return
    if data == "screen:account":
        await render_account(update, context)
        return
    if data in {"screen:home", "screen:menu"}:
        await render_menu(update, context)
        return
    if data.startswith("screen:"):
        target = data.split(":", 1)[1]
        routes = {"price": render_price, "signal": render_signal, "analysis": render_analysis, "activate": render_activate, "access": render_activate, "renew": render_renew, "history": render_history, "settings": render_settings, "support": render_support, "help": render_help}
        handler = routes.get(target)
        if handler:
            if target in {"price", "signal", "analysis"}:
                await _answer_loading(update)
            await handler(update, context)
        return
    if data.startswith("refresh:"):
        target = data.split(":", 1)[1]
        routes = {"price": render_price, "signal": render_signal, "analysis": render_analysis}
        handler = routes.get(target)
        if handler:
            await _answer_loading(update)
            await handler(update, context)
        return
    if data.startswith("retry:"):
        target = data.split(":", 1)[1]
        routes = {"price": render_price, "signal": render_signal, "analysis": render_analysis}
        handler = routes.get(target)
        if handler:
            await _answer_loading(update)
            await handler(update, context)
        return
    if data.startswith("lang:"):
        lang = data.split(":", 1)[1]
        if lang not in LANGUAGES:
            lang = "en"
        database.set_user_language(query.from_user.id, lang)
        await query.answer(t(lang, "saved"), show_alert=False)
        await render_menu(update, context)
        return
    if data == "settings:language":
        await query.answer()
        lang = _lang(update)
        terminal = "\n".join(["[ LANGUAGE SELECTOR ]", t(lang, "choose_language"), t(lang, "language_names")])
        await _present(update, _screen(update, terminal, f">> {t(lang, 'language')} // {t(lang, 'language_value')}"), language_keyboard(update))
        return
    if data == "action:token":
        await query.answer()
        context.user_data["awaiting_token"] = True
        lang = _lang(update)
        await query.message.reply_text(f"{t(lang, 'enter_activation')}\n{t(lang, 'token_note')}", parse_mode="HTML", reply_markup=access_keyboard(update))
        return


async def unknown_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Never leave an unknown command unanswered."""
    await update.message.reply_text(f'<b>[ ERROR ]: COMMAND_NOT_RECOGNIZED</b>\n\n>> {t(_lang(update), 'unknown_cmd_hint')}', parse_mode='HTML', reply_markup=access_keyboard(update))

async def unknown_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle arbitrary customer text without silently ignoring it."""
    if context.user_data.get('awaiting_token'):
        await token_text_handler(update, context)
        return
    await update.message.reply_text(f'<b>[ ERROR ]: INPUT_NOT_RECOGNIZED</b>\n\n>> {t(_lang(update), 'unknown_input_hint')}', parse_mode='HTML', reply_markup=access_keyboard(update))

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    logger.error('Unhandled exception: %s', error, exc_info=error)
    if ADMIN_TELEGRAM_ID:
        try:
            who = '?'
            if isinstance(update, Update) and update.effective_user:
                who = str(update.effective_user.id)
            await context.bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text=f'<b>⚠ UNHANDLED ERROR</b>\n{DIVIDER}\n{_esc(error.__class__.__name__)}: {_esc(str(error))[:300]}\nUSER: <code>{who}</code>', parse_mode='HTML')
        except Exception:
            logger.exception('Failed to alert admin about unhandled error')
    if isinstance(update, Update):
        query = update.callback_query
        if query:
            try:
                await query.edit_message_text(f'<b>[ FAULT ]: Module temporarily unavailable.</b>\n\n>> {t(_lang(update), 'tap_menu_retry')}', parse_mode='HTML', reply_markup=home_keyboard(update))
            except Exception:
                pass
        elif update.message:
            try:
                await update.message.reply_text(f'[ FAULT ]: TEMPORARY SERVICE ERROR\n>> {t(_lang(update), 'try_again')}', parse_mode='HTML', reply_markup=home_keyboard(update))
            except Exception:
                pass

async def post_init(application: Application) -> None:
    database.init_db()
    try:
        await application.bot.set_my_short_description(SHORT_DESCRIPTION)
        await application.bot.set_my_description(BOT_DESCRIPTION)
        logger.info('Telegram premium profile metadata configured.')
    except Exception as exc:
        logger.warning('Could not configure Telegram profile metadata: %s', exc)

def setup_logging() -> None:
    log_level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(log_level)
    if not root.handlers:
        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(log_level)
        sh.setFormatter(logging.Formatter(LOG_FORMAT))
        root.addHandler(sh)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.WARNING)

def build_application() -> Application:
    """Build the Telegram application for Belmo webhook processing."""
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(CommandHandler('token', token_command))
    application.add_handler(CommandHandler('status', lambda u, c: render_account(u, c)))
    application.add_handler(CommandHandler('addtoken', addtoken_command))
    application.add_handler(CommandHandler('listusers', listusers_command))
    application.add_handler(CommandHandler('revoke', revoke_command))
    application.add_handler(CommandHandler('fulfillment', fulfillment_command))
    application.add_handler(CommandHandler('reconcile', reconcile_command))
    application.add_handler(CommandHandler('user', user_command))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command_handler))
    application.add_handler(MessageHandler(filters.TEXT, unknown_text_handler))
    application.add_handler(CallbackQueryHandler(callback_router))
    application.add_error_handler(global_error_handler)
    return application

def main() -> None:
    """Local-development fallback only. Belmo production uses app.py + webhook."""
    setup_logging()
    database.init_db()
    application = build_application()
    logger.info('Starting local polling mode.')
    application.run_polling(drop_pending_updates=True)
if __name__ == '__main__':
    main()
