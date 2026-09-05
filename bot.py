from __future__ import annotations

import asyncio
import logging

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

# Telegram does not expose the user's viewport width to bot messages. Keep a
# mobile-optimized terminal width that fills the message bubble without
# forcing horizontal overflow on common phone layouts.
TERMINAL_WIDTH = 52
TERMINAL_INNER_WIDTH = TERMINAL_WIDTH - 2


def _terminal(lines: list[str]) -> str:
    """Render every bot panel inside one consistent mobile-width terminal."""
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
    return '<pre>' + '\n'.join(framed) + '</pre>'


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
        'XAU/USD MARKET INTELLIGENCE',
        '',
        'STATUS : ONLINE',
        'BOT    : MEMBER BONUS',
        '',
        'Premium Channel is the primary',
        'Neural Gold product. This bot is',
        'a bonus utility for channel members.',
    ])


HELP_TEXT = _terminal([
    '[ NEURAL GOLD / HOW IT WORKS ]',
    '',
    '01 PAYMENT : Neural Gold on Whop',
    '02 ACCESS  : Premium Channel',
    '03 CONTENT : Neural Strikes',
    '04 BONUS   : Telegram bot',
    '',
    '[ BOT BONUS ]',
    'The bot is not the purchase gate.',
    'Premium Channel membership gives',
    'the bot its member-only context.',
    '',
    '[ STATUS ]',
    'LONG      : bullish',
    'SHORT     : bearish',
    'HOLD      : setup not confirmed',
    'DATA GAP  : insufficient data',
    '',
    'Education only. Trading involves risk.',
])

BONUS_TEXT = _terminal([
    '[ NEURAL GOLD / BOT BONUS ]',
    '',
    'PRODUCT : PREMIUM CHANNEL',
    'BOT     : BONUS',
    '',
    'This Telegram bot is a bonus',
    'for Premium Channel members.',
    '',
    'Join the Premium Channel through',
    'your active Whop membership first.',
    '',
    'Then use this bot for signal lookup,',
    'access status and market information.',
])

ACCESS_INACTIVE_TEXT = _terminal([
    '[ BOT BONUS / INACTIVE ]',
    '',
    'CHANNEL : MEMBER ACCESS REQUIRED',
    '',
    'The Telegram bot is a bonus for',
    'members of the Premium Channel.',
    '',
    'Complete your Neural Gold purchase',
    'on Whop and join the Premium Channel',
    'before using member-only bot features.',
])

ACCESS_ACTIVE_TEXT = _terminal([
    '[ BOT BONUS / ACTIVE ]',
    '',
    'CHANNEL : MEMBER',
    'BOT     : BONUS ACTIVE',
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
    'Use the menu below to continue.',
    '',
    'Available:',
    'LATEST SIGNAL',
    'ACCESS STATUS',
    'BOT BONUS',
    'HOW IT WORKS',
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
            InlineKeyboardButton('📡 LATEST SIGNAL', callback_data='signal'),
            InlineKeyboardButton('📊 ACCESS STATUS', callback_data='status'),
        ],
        [
            InlineKeyboardButton('🎁 BOT BONUS', callback_data='bonus'),
            InlineKeyboardButton('ℹ️ HOW IT WORKS', callback_data='help'),
        ],
    ])


def _is_message_not_modified(exc: BadRequest) -> bool:
    """Return True when Telegram reports an idempotent edit as a no-op."""
    return 'message is not modified' in str(exc).lower()


async def _edit_message(target, text: str) -> None:
    """Edit a callback message without turning Telegram no-ops into errors."""
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
    """Give every unsupported command or text input a useful English fallback."""
    if update.message is not None:
        await update.message.reply_text(UNKNOWN_INPUT_TEXT, parse_mode='HTML', reply_markup=main_menu())


async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == 'home':
        await _edit_message(query, _main_menu_text())
        return
    if query.data == 'help':
        await _edit_message(query, HELP_TEXT)
        return
    if query.data == 'bonus':
        await _edit_message(query, BONUS_TEXT)
        return
    if query.data == 'status':
        text, _ = await _status_text(query.from_user.id, context.bot)
        await _edit_message(query, text)
        return
    if query.data == 'signal':
        await _send_signal(query, query.from_user.id, context.bot)
        return
    await _edit_message(query, UNKNOWN_INPUT_TEXT)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Log internal errors and return a safe user-facing fallback when possible."""
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
