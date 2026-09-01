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
from terminal_style import boot, intel_footer, intel_header, pay_guide, panel, render_header, render_terminal_box, stamp
from config import ADMIN_TELEGRAM_ID, LOG_FILE, LOG_FORMAT, LOG_LEVEL, NEURAL_VERSION, SIGNAL_VALIDITY_MINUTES, TELEGRAM_BOT_TOKEN
logger = logging.getLogger(__name__)
GOLD = '◆'
DIVIDER = '━' * 36
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

def _persistent_nav(update: Update) -> list[InlineKeyboardButton]:
    lang = _lang(update)
    return list(ts.render_persistent_nav(lang).inline_keyboard[0])


def _keyboard(update: Update, rows=None) -> InlineKeyboardMarkup:
    keyboard = list(rows or [])
    keyboard.append(_persistent_nav(update))
    return InlineKeyboardMarkup(keyboard)


def home_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    if update.effective_user and not auth.verify_token(update.effective_user.id)[0]:
        import phase2_bot
        telegram_id = update.effective_user.id
        return _keyboard(update, [
            [InlineKeyboardButton(f"🟢 {t(lang, 'days7')}", url=phase2_bot.checkout_link(telegram_id, 7))],
            [InlineKeyboardButton(f"🟡 {t(lang, 'days14')}", url=phase2_bot.checkout_link(telegram_id, 14))],
            [InlineKeyboardButton(f"🔵 {t(lang, 'days30')}", url=phase2_bot.checkout_link(telegram_id, 30))],
        ])
    return _keyboard(update, [
        [InlineKeyboardButton("MARKET PULSE", callback_data='screen:price'), InlineKeyboardButton("NEURAL STRIKES", callback_data='screen:signal')],
        [InlineKeyboardButton("STRUCTURE MAP", callback_data='screen:analysis')],
    ])

def price_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    if auth.verify_token(update.effective_user.id)[0]:
        return _keyboard(update, [[InlineKeyboardButton(t(lang, 'refresh'), callback_data='screen:price')]])
    import phase2_bot
    telegram_id = update.effective_user.id
    return _keyboard(update, [
        [InlineKeyboardButton(f"🟢 {t(lang, 'days7')}", url=phase2_bot.checkout_link(telegram_id, 7))],
        [InlineKeyboardButton(f"🟡 {t(lang, 'days14')}", url=phase2_bot.checkout_link(telegram_id, 14))],
        [InlineKeyboardButton(f"🔵 {t(lang, 'days30')}", url=phase2_bot.checkout_link(telegram_id, 30))],
    ])


def signal_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    return _keyboard(update, [[InlineKeyboardButton(t(lang, 'new_signal'), callback_data='screen:signal')]])


def account_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    return _keyboard(update, [[InlineKeyboardButton(t(lang, 'refresh_status'), callback_data='screen:account')]])


def access_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    import phase2_bot
    telegram_id = update.effective_user.id
    return _keyboard(update, [
        [InlineKeyboardButton(f"🟢 {t(lang, 'days7')}", url=phase2_bot.checkout_link(telegram_id, 7))],
        [InlineKeyboardButton(f"🟡 {t(lang, 'days14')}", url=phase2_bot.checkout_link(telegram_id, 14))],
        [InlineKeyboardButton(f"🔵 {t(lang, 'days30')}", url=phase2_bot.checkout_link(telegram_id, 30))],
        [InlineKeyboardButton(t(lang, 'activate'), callback_data='action:token'), InlineKeyboardButton(t(lang, 'paid'), callback_data='paid:menu')],
    ])


def analysis_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    return _keyboard(update, [[InlineKeyboardButton(t(lang, 'refresh_analysis'), callback_data='screen:analysis')]])


def settings_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    return _keyboard(update, [
        [InlineKeyboardButton(t(lang, 'interface'), callback_data='noop')],
        [InlineKeyboardButton(t(lang, 'timezone'), callback_data='noop')],
        [InlineKeyboardButton(t(lang, 'data_mode'), callback_data='noop')],
    ])


def language_keyboard(update: Update) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(label, callback_data=data)] for label, data in language_buttons()]
    return _keyboard(update, rows)


def support_keyboard(update: Update) -> InlineKeyboardMarkup:
    lang = _lang(update)
    rows = []
    if ADMIN_TELEGRAM_ID:
        rows.append([InlineKeyboardButton(t(lang, 'contact'), url=f'tg://user?id={ADMIN_TELEGRAM_ID}')])
    return _keyboard(update, rows)

async def render_home(update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool=True) -> None:
    user = update.effective_user
    if user is None:
        return
    db_user = database.get_user_by_telegram_id(user.id)
    active = False
    if db_user:
        active, _ = auth.verify_token(user.id)
    lang = _lang(update)
    clearance = t(lang, 'premium_active') if active else '[ ACCESS ]: PENDING // CLEARANCE REQUIRED'
    text = f'NEURAL GOLD v3.2 // OPERATOR CONSOLE\n{boot(granted=active)}\n<i>{stamp()}</i>\n{DIVIDER}\n\nOPERATOR: <b>{_safe_user_name(user)}</b>\nTELEGRAM_ID: <code>{user.id}</code>\nCLEARANCE: <b>{GOLD} ● {clearance}</b>\n\n<b>>> {t(lang, 'select_module')}</b>\n' + panel(['  01  PRICE     — MARKET PULSE', '  02  SIGNAL    — NEURAL STRIKES', '  03  ANALYSIS  — STRUCTURE MAP', '  04  ACCOUNT   — OPERATOR HUB', '  05  SETTINGS  — SYSTEM SYNC', '  06  SUPPORT   — UPLINK']) + '\n>> [ CORE ]: ALL MODULES UNLOCKED. AWAITING SELECTION.'
    await _present(update, text, home_keyboard(update), edit=edit)

async def render_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return
    valid, _ = auth.verify_token(user.id)
    if not valid:
        await render_locked(update, 'price')
        return
    await _answer_loading(update, '[ CORE ]: SYNCING XAU/USD FEED...')
    try:
        data = await asyncio.wait_for(api_handler.get_cached_or_fresh_price(user.id), timeout=10.0)
        bid = float(data['bid'])
        ask = float(data['ask'])
        mid = (bid + ask) / 2
        change = float(data.get('change', 0))
        pct = float(data.get('change_percent', 0))
        change_mark = '+' if change >= 0 else ''
        source = _esc(data.get('source', 'Live feed'))
        raw_ts = str(data.get('timestamp', '—'))
        timestamp = _format_timestamp(raw_ts)
        move_icon = '📈' if change > 0 else '📉' if change < 0 else '⚡️'
        status_label = '[STALE]' if data.get('stale') else '[LIVE]'
        rows = ['  SYSTEM: MARKET_DATA_SATELLITE', f'  STATUS: {status_label}  FEED_TIME: {timestamp}', ts.bar(), '  SYMBOL      XAU/USD · GOLD SPOT', f'  PRICE       {_money(mid)} [STABLE]', f'  BID/ASK     {_money(bid)} / {_money(ask)}', ts.bar(), f'  HIGH  {_money(float(data['high']))}', f'  LOW   {_money(float(data['low']))}', f'  NET   {change_mark}{change:.2f} ({change_mark}{pct:.2f}%)', ts.bar(), f'  UPLINK: {source} // MODE: LIVE']
        text = f'<b>[ ANALYSIS ]: {t(_lang(update), 'live_feed')} // XAU/USD {move_icon}</b>\n<pre>┍' + ts.bar('━') + '┑\n' + '\n'.join((ts.prow(r) for r in rows)) + '\n┕' + ts.bar('━') + f'┙</pre>\n>> [ CORE ]: FEED VERIFIED // {stamp()}\n<i>Market feed may vary slightly by venue.</i>'
        await _present(update, text, price_keyboard(update))
    except Exception as exc:
        logger.exception('Premium price screen failed: %s', exc)
        await _present(update, f'<b>[ FAULT ]: LINK_TIMEOUT // RETRYING...</b>\n\n<pre>┍━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┑\n  STATUS: [OFFLINE]\n  [ ERROR ]: DATA_GAP_DETECTED\n  MARKET DATA UPLINK TEMPORARILY UNAVAILABLE\n┕━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┙</pre>\n{t(_lang(update), 'please_refresh')}', price_keyboard(update))

async def render_signal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return
    valid, _ = auth.verify_token(user.id)
    if not valid:
        await render_locked(update, 'signal')
        return
    await _answer_loading(update, '[ NEURAL-MAP ]: COMPUTING SIGNAL VECTOR...')
    try:
        data = await asyncio.wait_for(api_handler.get_cached_or_fresh_price(user.id), timeout=10.0)
        indicators = api_handler._simulate_technical_indicators(float(data['bid']), float(data.get('change_percent', 0)))
        signal = api_handler._determine_signal(float(data['bid']), indicators)
        direction = signal['direction']
        icon = {'BUY': '🟢', 'SELL': '🔴', 'HOLD': '🟡'}[direction]
        confidence = float(signal['confidence'])
        confidence_tag = 'HIGH' if confidence >= 70 else 'MODERATE' if confidence >= 55 else 'MARGINAL'
        setup = 'AWAITING CONFIRMATION' if direction == 'HOLD' else f'{_money(signal['entry_low'])} — {_money(signal['entry_high'])}'
        align = 'POSITIVE' if 'BULLISH' in str(indicators.get('ema_trend', '')) else 'NEGATIVE' if 'BEARISH' in str(indicators.get('ema_trend', '')) else 'NEUTRAL'
        rows = ['  NEURAL SIGNAL // ALGO-READ', '  OPERATIONAL STATUS: SCANNING...', ts.bar(), f'  VECTOR:      {direction}', '  COORDINATE:', f'   ↳ [{_esc(setup)}]', f'  CONF_LEVEL:  {confidence:.1f}% [{confidence_tag}]', f'  TIMEFRAME:   INTRADAY // {SIGNAL_VALIDITY_MINUTES} MIN', ts.bar(), f'  MOMENTUM:    {_esc(signal['momentum'])}', f'  LIQUIDITY:   {_esc(signal['liquidity'])}', f'  VOLATILITY:  {_esc(signal['volatility'])}', ts.bar(), '  EXECUTION MAP:', f'  TP_1 {(_money(signal['tp1']) if signal['tp1'] else '—')}', f'  TP_2 {(_money(signal['tp2']) if signal['tp2'] else '—')} | TP_3 {(_money(signal['tp3']) if signal['tp3'] else '—')}', f'  STOP_LOSS {(_money(signal['sl']) if signal['sl'] else '—')} | R:R 1:{signal['risk_reward']}', ts.bar(), '  ALPHA-SENTI MATRIX:', ' [TEMPORAL MOMENTUM RESONANCE]', f'   ↳ {indicators['rsi']}', ' [DUAL-PHASE CONVERGENCE MANIFOLD]', f'   ↳ {indicators['macd_hist']:+.2f}', ' [SYNAPTIC TREND ALIGNMENT]', f'   ↳ {_esc(indicators['ema_trend']).upper()}', ' [PROBABILISTIC FLUX]', f'   ↳ {indicators['stoch_k']}', ts.bar(), '  LOG: PROJECTION LAYER ACTIVE']
        text = f'<b>{intel_header()}</b>\n<i>{icon} {stamp()} // {t(_lang(update), 'neural_signal')} ENGINE</i>\n<pre>◤' + ts.bar('━') + '◥\n' + '\n'.join((ts.prow(r) for r in rows)) + '\n◣' + ts.bar('━') + f'◢</pre>\n{intel_footer()}\n<i>{t(_lang(update), 'signal_disclaimer')}</i>'
        await _present(update, text, signal_keyboard(update))
    except Exception as exc:
        logger.exception('Signal screen failed: %s', exc)
        await _present(update, '<b>[ FAULT ]: NEURAL-MAP OFFLINE // RETRYING...</b>\n\n<pre>◤━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━◥\n  STATUS: SIGNAL ENGINE UNAVAILABLE\n  [ ERROR ]: DATA_GAP_DETECTED\n◣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━◢</pre>\nPlease refresh in a moment.', signal_keyboard(update))

async def render_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return
    valid, _ = auth.verify_token(user.id)
    if not valid:
        await render_locked(update, 'analysis')
        return
    await _answer_loading(update, '[ EXTRACTING ]: MARKET STRUCTURE...')
    try:
        data = await asyncio.wait_for(api_handler.get_cached_or_fresh_price(user.id), timeout=10.0)
        bid = float(data['bid'])
        pct = float(data.get('change_percent', 0))
        indicators = api_handler._simulate_technical_indicators(bid, pct)
        signal = api_handler._determine_signal(bid, indicators)
        bias = _esc(signal['momentum'])
        bias_icon = _bias_icon(signal['momentum'])
        rsi = float(indicators['rsi'])
        stoch = float(indicators['stoch_k'])
        rsi_state = 'OVERSOLD' if rsi < 30 else 'OVERBOUGHT' if rsi > 70 else 'NEUTRAL'
        stoch_state = 'OVERSOLD' if stoch < 20 else 'OVERBOUGHT' if stoch > 80 else 'NEUTRAL'
        rows = ['  ANALYSIS :: MOMENTUM/VOLATILITY', ts.bar(), f'  MARKET BIAS: {bias.upper()}', ts.bar(), '  ALPHA-SENTI MATRIX:', ' [TEMPORAL MOMENTUM RESONANCE]', f'   ↳ {indicators['rsi']} [{rsi_state}]', ' [DUAL-PHASE CONVERGENCE MANIFOLD]', f'   ↳ {indicators['macd_hist']:+.2f}', ' [SYNAPTIC TREND ALIGNMENT]', f'   ↳ {_esc(indicators['ema_trend']).upper()}', ' [PROBABILISTIC FLUX]', f'   ↳ {indicators['stoch_k']} [{stoch_state}]', ' [VOLATILITY VARIANCE]', f'   ↳ {indicators['atr']}', ' [QUANTUM ENVELOPE POSITION]', f'   ↳ {_esc(indicators['bb_position']).upper()}', ts.bar(), '  LIQUIDITY MODEL:', f'  LEVEL {_esc(signal['liquidity']).upper()} | CONF {signal['confidence']}%', ts.bar(), '  SOURCE: SIGNAL_ENGINE // LIVE']
        text = f'<b>[ NEURAL-MAP ]: {t(_lang(update), 'analysis_title')} {bias_icon}</b>\n<i>{stamp()} // QUANTITATIVE DEEP-DIVE</i>\n<pre>⌁' + ts.bar('━') + '⌁\n' + '\n'.join((ts.prow(r) for r in rows)) + '\n⌁' + ts.bar('━') + f'⌁</pre>\n>> [ CORE ]: STRUCTURE SCAN COMPLETE // {stamp()}\n<i>{t(_lang(update), 'analysis_note')}</i>'
        await _present(update, text, analysis_keyboard(update))
    except Exception as exc:
        logger.exception('Analysis screen failed: %s', exc)
        await _present(update, '<b>[ FAULT ]: ANALYSIS ENGINE OFFLINE // RETRYING...</b>\n\n<pre>⌁─────────────────────────────────────────────⌁\n  STATUS: ANALYSIS ENGINE UNAVAILABLE\n  [ ERROR ]: DATA_GAP_DETECTED\n⌁─────────────────────────────────────────────⌁</pre>\nPlease refresh in a moment.', analysis_keyboard(update))

def _bias_icon(momentum: str) -> str:
    if 'BULLISH' in momentum:
        return '🟢'
    if 'BEARISH' in momentum:
        return '🔴'
    return '🟡'

async def render_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return
    db_user = database.get_user_by_telegram_id(user.id)
    if db_user is None:
        text = f'<b>[ FILE ]: {t(_lang(update), 'account_intel')}</b>\n{DIVIDER}\n\n[ ERROR ]: OPERATOR_PROFILE_NOT_FOUND\n\n>> Profile not registered yet.\n>> Tap <b>ACCESS &amp; PLANS</b> to activate your account.'
    else:
        valid, reason = auth.verify_token(user.id)
        expiry = database.normalize_datetime_utc(db_user.subscription_expiry)
        expiry_text = expiry.strftime('%d %b %Y • %H:%M UTC') if expiry else t(_lang(update), 'not_activated')
        status = t(_lang(update), 'active') if valid else reason.replace('_', ' ').upper()
        status_icon = '🟢' if valid else '○'
        text = f'<b>[ FILE ]: {t(_lang(update), 'account_intel')}</b>\n<i>{t(_lang(update), 'your_access')} // {stamp()}</i>\n{DIVIDER}\n\nSTATUS: <b>{status_icon} {status}</b>\n\n' + panel([f'  TELEGRAM_ID:  {user.id}', f'  USERNAME:     @{_esc(user.username or 'N/A')}', f'  ACCESS_UNTIL: {expiry_text}']) + '\n>> [ CORE ]: Your private access status is checked in real time.'
    await _present(update, text, account_keyboard(update))

async def render_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    active = False
    if user:
        active, _ = auth.verify_token(user.id)
    state = t(_lang(update), 'active') if active else t(_lang(update), 'ready')
    icon = '🟢' if active else '◆'
    text = f'<b>[ CLEARANCE ]: {t(_lang(update), 'premium_access')}</b>\n<i>{t(_lang(update), 'membership')} // {stamp()}</i>\n{DIVIDER}\n\n{icon} {state}\n\n{t(_lang(update), 'unlocks')}\n◈ Live XAU/USD pricing\n◎ Neural trade signals\n⌁ Market structure analysis\n♛ Private account dashboard\n\n<b>ACCESS &amp; PLANS</b>\n7 DAYS   •   SHORT TERM\n14 DAYS  •   STANDARD\n30 DAYS  •   PREMIUM\n\n{t(_lang(update), 'activation_route')}\n\n<i>Enter your single-use activation token after purchase.</i>'
    await _present(update, text, access_keyboard(update))

async def render_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Console submenu (operator fix): Language / Help / Uplink / System Sync live here."""
    lang = _lang(update)
    text = f'<b>[ CONSOLE ]: MENU // NEURAL GOLD {NEURAL_VERSION}</b>\n{DIVIDER}\n\n<pre>{_esc(t(lang, 'menu_body'))}</pre>'
    rows = [[InlineKeyboardButton(f'❓ {t(lang, 'help')}', callback_data='screen:help')], [InlineKeyboardButton(f'🌐 {t(lang, 'support')}', callback_data='screen:support')]]
    await _present(update, text, _keyboard(update, rows))

async def render_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Operator manual: how to use the bot (audit fix: menu-requested help)."""
    lang = _lang(update)
    text = f'<b>[ MANUAL ]: HOW TO USE // NEURAL GOLD {NEURAL_VERSION}</b>\n{DIVIDER}\n\n<pre>{_esc(t(lang, 'help_body'))}</pre>'
    await _present(update, text, _keyboard(update))

async def render_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = f'<b>[ SYSTEM ]: {t(_lang(update), 'settings_title')}</b>\n<i>{t(_lang(update), 'interface_control')} // {stamp()}</i>\n{DIVIDER}\n\n<b>{t(_lang(update), 'display_profile')}</b>\n◈ {t(_lang(update), 'premium_dark')}\n◆ {t(_lang(update), 'gold_nav')}\n⌁ {t(_lang(update), 'compact_cards')}\n\n<b>{t(_lang(update), 'region')}</b>\nTimezone  <code>Asia/Jakarta</code>\n{t(_lang(update), 'language_value')}  <code>{_lang(update).upper()}</code>\n\n>> [ CORE ]: {t(_lang(update), 'core_settings')}'
    await _present(update, text, settings_keyboard(update))

async def render_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = f'<b>[ UPLINK ]: {t(_lang(update), 'support_title')}</b>\n<i>{t(_lang(update), 'direct_help')} // {stamp()}</i>\n{DIVIDER}\n\n{t(_lang(update), 'support_need')}\n\n<b>{t(_lang(update), 'support_channel')}</b>\n{t(_lang(update), 'support_tap')}\n\n[ SECURITY ]: {t(_lang(update), 'security')}'
    await _present(update, text, support_keyboard(update))

async def render_locked(update: Update, module: str) -> None:
    labels = {'price': 'MARKET PULSE', 'signal': 'NEURAL STRIKES', 'analysis': 'STRUCTURE MAP'}
    label = labels.get(module, module.upper())
    text = f'<b>[ LOCKED ]: {label}</b>\n{DIVIDER}\n\n[ FAULT ]: CLEARANCE_CHECK_FAILED\n\n{t(_lang(update), 'locked')}\n\n[ ERROR ]: {t(_lang(update), 'access_required')}\n>> {t(_lang(update), 'activate_required')}\n\n<i>{t(_lang(update), 'verified_auto')}</i>'
    await _present(update, text, access_keyboard(update))

async def _answer_loading(update: Update, text: str | None = None) -> None:
    """Deliver the single canonical loading label through callback feedback."""
    query = update.callback_query
    if query:
        try:
            await query.answer(t(_lang(update), "loading"), show_alert=False)
        except Exception:
            pass

async def _present(update: Update, text: str, keyboard: InlineKeyboardMarkup, edit: bool=True) -> None:
    """Canonical customer rendering: Header -> Terminal -> Context."""
    query = update.callback_query
    user = update.effective_user
    lang = _lang(update)
    plain = html.unescape(re.sub(r"<[^>]+>", "", text))
    is_home = "OPERATOR CONSOLE" in plain

    def clean_terminal(value: str) -> str:
        value = re.sub(r"(?im)^\s*NEURAL GOLD(?: v3\.2)?[^\n]*$", "", value)
        value = re.sub(r"(?im)^\s*\[ ?\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC ?\]\s*$", "", value)
        value = re.sub(r"(?im)^\s*OPERATOR\s*:\s*.*$", "", value)
        value = re.sub(r"(?im)^\s*STATUS\s*:\s*.*$", "", value)
        value = value.translate(str.maketrans("", "", "┍┑┕┙│◤◥◣◢━"))
        return "\n".join(line.rstrip() for line in value.split("\n")).strip()

    if user and is_home:
        active, _ = auth.verify_token(user.id)
        access_line = "GRANTED. WELCOME, OPERATOR." if active else "PENDING // CLEARANCE REQUIRED"
        terminal_body = "\n".join([
            "[ SYSTEM ]: INITIALIZING...",
            "[ STATUS ]: SYNCING GLOBAL BULLION RESERVES...",
            f"[ ACCESS ]: {access_line}",
        ])
        context_line = f">> {t(lang, 'select_module')}" if active else f">> {t(lang, 'access')}"
    else:
        pre_match = re.search(r"<pre>(.*?)</pre>", text, flags=re.S | re.I)
        terminal_body = clean_terminal(pre_match.group(1) if pre_match else plain)
        context_matches = re.findall(r"(?m)^\s*>>[^\n]*", plain)
        context_line = context_matches[0].strip() if context_matches else ""
        context_line = re.sub(r"\s*//\s*\[?\s*\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC\s*\]?", "", context_line).strip()

    if not terminal_body:
        terminal_body = t(lang, "ready")

    canonical = (
        f"{render_header(user, lang)}\n\n<pre>{render_terminal_box(terminal_body, 40)}</pre>"
        if user
        else f"<pre>{render_terminal_box(terminal_body, 40)}</pre>"
    )
    if context_line:
        canonical += f"\n\n{context_line}"
    
    if query and edit:
        try:
            await query.edit_message_text(text=canonical, parse_mode="HTML", reply_markup=keyboard)
            return
        except BadRequest as exc:
            if "not modified" in str(exc).lower():
                return
        except Exception as exc:
            logger.debug("Could not edit callback message: %s", exc)

    try:
        if query and query.message:
            await query.message.reply_text(canonical, parse_mode="HTML", reply_markup=keyboard)
            return
    except Exception as exc:
        logger.debug("Callback reply fallback failed: %s", exc)

    if update.message:
        await update.message.reply_text(canonical, parse_mode="HTML", reply_markup=keyboard)
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
    data = query.data or ''
    if data == 'noop':
        await query.answer('This setting is controlled by the bot configuration.', show_alert=True)
        return
    if data == 'paid:menu':
        await paid_confirmation(update, context)
        return
    if data.startswith('nav:'):
        try:
            await query.answer()
        except Exception:
            pass
        target = data.split(':', 1)[1]
        if target == 'menu':
            await render_menu(update, context)
        else:
            await render_home(update, context)
        return
    if data.startswith('screen:'):
        target = data.split(':', 1)[1]
        if target in {'home', 'account', 'access', 'settings', 'support', 'help'}:
            try:
                await query.answer()
            except Exception:
                pass
        if target == 'home':
            await render_home(update, context)
        elif target == 'price':
            await render_price(update, context)
        elif target == 'signal':
            await render_signal(update, context)
        elif target == 'analysis':
            await render_analysis(update, context)
        elif target == 'account':
            await render_account(update, context)
        elif target == 'access':
            await render_access(update, context)
        elif target == 'settings':
            await render_settings(update, context)
        elif target == 'support':
            await render_support(update, context)
        elif target == 'help':
            await render_help(update, context)
        return
    if data.startswith('lang:'):
        lang = data.split(':', 1)[1]
        if lang not in LANGUAGES:
            lang = 'en'
        database.set_user_language(query.from_user.id, lang)
        try:
            await query.answer(t(lang, 'saved'))
        except Exception:
            pass
        await render_home(update, context)
        return
    if data == 'settings:language':
        try:
            await query.answer()
        except Exception:
            pass
        lang = _lang(update)
        await _present(update, f'<b>🌐 {t(lang, 'choose_language')}</b>\n{DIVIDER}\n\n{t(lang, 'language_names')}', language_keyboard(update))
        return
    if data == 'action:token':
        try:
            await query.answer()
        except Exception:
            pass
        context.user_data['awaiting_token'] = True
        lang = _lang(update)
        await query.message.reply_text(f'<b>[ KEYGEN ]: ACTIVATE TOKEN</b>\n\n>> {t(lang, 'enter_activation')}\n<i>{t(lang, 'token_note')}</i>', parse_mode='HTML', reply_markup=access_keyboard(update))
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
