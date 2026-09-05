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
        'CHANNEL: Premium Channel',
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
