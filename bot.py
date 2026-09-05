from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import access
import database
import signal_engine
from config import TELEGRAM_BOT_TOKEN

log = logging.getLogger('bot')

TERMINAL_WIDTH = 52
TERMINAL_INNER_WIDTH = TERMINAL_WIDTH - 2
TERMINAL_HEADER = 'NEURAL GOLD [SIGNALS]'
TERMINAL_FOOTER = 'XAU/USD • MEMBER BONUS'


def _terminal(lines: list[str]) -> str:
    """Render every bot panel with one consistent header, terminal, and footer."""
    body: list[str] = []
    for line in lines:
        text = str(line).replace('<', '&lt;').replace('>', '&gt;')
        if len(text) <= TERMINAL_INNER_WIDTH:
            body.append(text)
            continue
        words = text.split()
        current = ''
        for word in words:
            while len(word) > TERMINAL_INNER_WIDTH:
                if current:
                    body.append(current)
                    current = ''
                body.append(word[:TERMINAL_INNER_WIDTH])
                word = word[TERMINAL_INNER_WIDTH:]
            if not word:
                continue
            candidate = word if not current else f'{current} {word}'
            if len(candidate) <= TERMINAL_INNER_WIDTH:
                current = candidate
            else:
                if current:
                    body.append(current)
                current = word
        if current:
            body.append(current)
    border = '+' + '-' * TERMINAL_INNER_WIDTH + '+'
    framed = [border] + [f'|{line:<{TERMINAL_INNER_WIDTH}}|' for line in body] + [border]
    terminal = '\n'.join(framed)
    return f'{TERMINAL_HEADER}\n\n<pre>{terminal}</pre>\n\n{TERMINAL_FOOTER}'


def _terminal_signal_lines(result: dict) -> list[str]:
    signal = result.get('signal', 'HOLD')
    lines = [
        '[ NEURAL STRIKES ]',
        f'SIGNAL : {signal}',
        f'STR    : {result.get("setup_strength", 0)}/100',
        f'TREND  : {result.get("trend", "NEUTRAL")}',
    ]
    if result.get('rsi') is not None:
        lines.append(f'RSI    : {result["rsi"]}')
    if result.get('entry') is not None:
        lines.append(f'ENTRY  : {result["entry"]}')
    for index, target in enumerate((result.get('tp') or [])[:3], start=1):
        lines.append(f'TP{index:<5}: {target}')
    if result.get('stop') is not None:
        lines.append(f'STOP   : {result["stop"]}')
    if result.get('risk_reward'):
        lines.append(f'R:R    : {result["risk_reward"]}')
    lines.extend([
        f'DATA   : {result.get("samples", 0)} samples',
        f'STATE  : {result.get("reason", "UNKNOWN")}',
        '',
        'Setup strength is not a win',
        'probability and is not guaranteed.',
        'Education only. Trade at your own risk.',
    ])
    return lines


def _format_signal(result: dict) -> str:
    return _terminal(_terminal_signal_lines(result))


def _main_menu_text() -> str:
    return _terminal([
        '[ NEURAL GOLD ]',
        'Neural Gold [SIGNALS]',
        'XAU/USD MARKET INTELLIGENCE',
        '',
        'STATUS : ONLINE',
        'BOT    : MEMBER BONUS',
        'ACCESS : Premium Channel',
        '',
        'Select a terminal view below.',
        'LIVE MARKET FEED',
        'NEURAL SIGNAL',
        'MARKET ANALYSIS',
        'SYSTEM SETTING',
    ])


def _system_info_text(access_active: bool) -> str:
    access_status = 'ACTIVE' if access_active else 'INACTIVE'
    channel_status = 'VERIFIED' if access_active else 'MEMBER ACCESS REQUIRED'
    return _terminal([
        '[ SYSTEM SETTING ]',
        '',
        '[ SYSTEM ]',
        'BOT STATUS     : ONLINE',
        'SERVICE        : NEURAL GOLD',
        'MARKET         : XAU/USD',
        'TIMEFRAME      : M5',
        '',
        '[ ACCESS ]',
        f'ACCESS STATUS  : {access_status}',
        f'PREMIUM CHANNEL: {channel_status}',
        '',
        '[ BOT BONUS ]',
        'BOT ROLE       : MEMBER BONUS',
        'PURCHASE GATE  : PREMIUM CHANNEL',
        '',
        '[ HOW IT WORKS ]',
        '01 PAYMENT : Neural Gold on Whop',
        '02 ACCESS  : Premium Channel',
        '03 CONTENT : Neural Strikes',
        '04 BONUS   : Telegram bot',
        '',
        'The bot is a bonus utility, not the',
        'purchase gate. Premium membership',
        'provides member-only bot context.',
        '',
        '[ INFORMATION ]',
        'Use Market Feed for live conditions.',
        'Use Neural Signal for the current',
        'actionable setup when access is active.',
        'Use Market Analysis for indicators',
        'and the current market interpretation.',
        '',
        'Education only. Trading involves risk.',
    ])


HELP_TEXT = _system_info_text(False)
BONUS_TEXT = _system_info_text(False)

ACCESS_INACTIVE_TEXT = _terminal([
    '[ SYSTEM / ACCESS ]',
    '',
    'ACCESS STATUS  : INACTIVE',
    'PREMIUM CHANNEL: MEMBER ACCESS REQUIRED',
    '',
    'The Telegram bot is a bonus for',
    'members of the Premium Channel.',
    '',
    'Complete your Neural Gold purchase',
    'on Whop and join the Premium Channel',
    'before using member-only bot features.',
])

ACCESS_ACTIVE_TEXT = _terminal([
    '[ SYSTEM / ACCESS ]',
    '',
    'ACCESS STATUS  : ACTIVE',
    'PREMIUM CHANNEL: VERIFIED',
    'BOT            : BONUS ACTIVE',
    '',
    'Your Premium Channel membership is',
    'confirmed by Telegram.',
    '',
    'Member-only bot features are active.',
])

UNKNOWN_INPUT_TEXT = _terminal([
    '[ NEURAL GOLD / INPUT ]',
    '',
    "I didn't recognize that input.",
    '',
    'Use the four terminal views below.',
    '',
    'LIVE MARKET FEED',
    'NEURAL SIGNAL',
    'MARKET ANALYSIS',
    'SYSTEM SETTING',
])

ERROR_TEXT = _terminal([
    '[ NEURAL GOLD / ERROR ]',
    '',
    'A temporary error occurred.',
    '',
    'Your request was not completed.',
    'Please use the menu below and',
    'try again.',
])


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton('📡 LIVE MARKET FEED', callback_data='market'),
            InlineKeyboardButton('⚡ NEURAL SIGNAL', callback_data='signal'),
        ],
        [
            InlineKeyboardButton('📊 MARKET ANALYSIS', callback_data='analysis'),
            InlineKeyboardButton('⚙️ SYSTEM SETTING', callback_data='system'),
        ],
    ])


def _is_message_not_modified(exc: BadRequest) -> bool:
    return 'message is not modified' in str(exc).lower()


async def _edit_message(target, text: str) -> None:
    try:
        await target.edit_message_text(text, parse_mode='HTML', reply_markup=main_menu())
    except BadRequest as exc:
        if _is_message_not_modified(exc):
            log.debug('telegram message edit was already up to date')
            return
        raise


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.to_thread(database.ensure_user, update.effective_user.id)
    await update.message.reply_text(_main_menu_text(), parse_mode='HTML', reply_markup=main_menu())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode='HTML', reply_markup=main_menu())


async def premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(BONUS_TEXT, parse_mode='HTML', reply_markup=main_menu())


async def _status_text(uid: int, bot) -> tuple[str, InlineKeyboardMarkup]:
    if not await access.has_access(bot, uid):
        return ACCESS_INACTIVE_TEXT, main_menu()
    return ACCESS_ACTIVE_TEXT, main_menu()


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, _ = await _status_text(update.effective_user.id, context.bot)
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=main_menu())


async def signal_text() -> str:
    samples = await asyncio.to_thread(database.recent_samples)
    return _format_signal(signal_engine.analyze(samples))


async def market_feed_text() -> str:
    samples = await asyncio.to_thread(database.recent_samples)
    if not samples:
        return _terminal([
            '[ LIVE MARKET FEED ]',
            '',
            'PRICE  : UNAVAILABLE',
            'CHANGE : UNAVAILABLE',
            'DATA   : 0 samples',
            'STATE  : DATA_GAP',
            '',
            'Waiting for the market data feed.',
        ])
    latest = samples[-1]
    timestamp = latest.get('ts')
    if isinstance(timestamp, datetime):
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        updated = timestamp.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    else:
        try:
            updated = datetime.fromtimestamp(float(timestamp), tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        except (TypeError, ValueError, OverflowError, OSError):
            updated = 'UNKNOWN'
    return _terminal([
        '[ LIVE MARKET FEED ]',
        '',
        f'XAU/USD : {latest.get("price", "UNAVAILABLE")}',
        f'CHANGE  : {latest.get("change_pct", "UNAVAILABLE")}',
        f'DATA    : {len(samples)} samples',
        f'UPDATED : {updated}',
        'SOURCE  : GOLD API',
        '',
        'Live market state only.',
        'Use Neural Signal for the current',
        'actionable setup.',
    ])


async def analysis_text() -> str:
    samples = await asyncio.to_thread(database.recent_samples)
    result = signal_engine.analyze(samples)
    return _terminal([
        '[ MARKET ANALYSIS ]',
        '',
        f'TREND  : {result.get("trend", "NEUTRAL")}',
        f'RSI    : {result.get("rsi") if result.get("rsi") is not None else "UNAVAILABLE"}',
        f'STR    : {result.get("setup_strength", 0)}/100',
        f'SIGNAL : {result.get("signal", "HOLD")}',
        f'STATE  : {result.get("reason", "UNKNOWN")}',
        f'DATA   : {result.get("samples", len(samples))} samples',
        f'TF     : {result.get("timeframe", "M5")}',
        '',
        'Analysis is derived from the same',
        'validated market data used by the',
        'Neural Signal engine.',
        '',
        'Education only. Trading involves risk.',
    ])


async def _send_signal(target, uid: int, bot) -> None:
    if not await access.has_access(bot, uid):
        if hasattr(target, 'edit_message_text'):
            await _edit_message(target, ACCESS_INACTIVE_TEXT)
        else:
            await target.reply_text(ACCESS_INACTIVE_TEXT, parse_mode='HTML', reply_markup=main_menu())
        return
    text = await signal_text()
    if hasattr(target, 'edit_message_text'):
        await _edit_message(target, text)
    else:
        await target.reply_text(text, parse_mode='HTML', reply_markup=main_menu())


async def signal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_signal(update.message, update.effective_user.id, context.bot)


async def link_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(BONUS_TEXT, parse_mode='HTML', reply_markup=main_menu())


async def unknown_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is not None:
        await update.message.reply_text(UNKNOWN_INPUT_TEXT, parse_mode='HTML', reply_markup=main_menu())


async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == 'home':
        await _edit_message(query, _main_menu_text())
        return
    if query.data == 'market':
        await _edit_message(query, await market_feed_text())
        return
    if query.data == 'signal':
        await _send_signal(query, query.from_user.id, context.bot)
        return
    if query.data == 'analysis':
        await _edit_message(query, await analysis_text())
        return
    if query.data == 'system':
        active = await access.has_access(context.bot, query.from_user.id)
        await _edit_message(query, _system_info_text(active))
        return
    if query.data == 'help' or query.data == 'bonus':
        active = await access.has_access(context.bot, query.from_user.id)
        await _edit_message(query, _system_info_text(active))
        return
    if query.data == 'status':
        text, _ = await _status_text(query.from_user.id, context.bot)
        await _edit_message(query, text)
        return
    await _edit_message(query, UNKNOWN_INPUT_TEXT)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.error('telegram handler failed', exc_info=context.error)
    try:
        if isinstance(update, Update) and update.callback_query is not None:
            await _edit_message(update.callback_query, ERROR_TEXT)
        elif isinstance(update, Update) and update.message is not None:
            await update.message.reply_text(ERROR_TEXT, parse_mode='HTML', reply_markup=main_menu())
    except Exception:
        log.exception('failed to send telegram error fallback')


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
    app.add_handler(MessageHandler(filters.COMMAND, unknown_input))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_input))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_error_handler(error_handler)
    return app
