from __future__ import annotations

import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

import access
import database
import signal_engine

log = logging.getLogger('bot')

# --- TERMINAL IDENTITY CONFIG ---
TERMINAL_WIDTH = 52
TERMINAL_INNER_WIDTH = TERMINAL_WIDTH - 2
TERMINAL_HEADER = 'NEURAL GOLD [SIGNALS]'
TERMINAL_FOOTER = 'XAU/USD • MEMBER BONUS'


def _terminal(lines: list[str]) -> str:
    """Render every bot panel with high-end institutional framing."""
    body = []
    for raw in lines:
        text = str(raw)
        if len(text) <= TERMINAL_INNER_WIDTH:
            body.append(text)
            continue
        words = text.split()
        current = ''
        for word in words:
            candidate = f'{current} {word}'.strip()
            if len(candidate) <= TERMINAL_INNER_WIDTH:
                current = candidate
            else:
                if current:
                    body.append(current)
                current = word
        if current:
            body.append(current)

    border = '┌' + '─' * TERMINAL_INNER_WIDTH + '┐'
    bottom_border = '└' + '─' * TERMINAL_INNER_WIDTH + '┘'
    framed = [border] + [f'│{line:<{TERMINAL_INNER_WIDTH}}│' for line in body] + [bottom_border]
    terminal = '\n'.join(framed)
    return f'{TERMINAL_HEADER}\n\n<pre>{terminal}</pre>\n\n{TERMINAL_FOOTER}'


def _terminal_signal_lines(result: dict) -> list[str]:
    signal = result.get('signal', 'HOLD')
    signal_icon = '🟢' if signal in {'BUY', 'SELL'} else '🟠'
    lines = [
        '[ ⚡ NEURAL SIGNAL ]',
        f'{signal_icon} SIGNAL  : {signal}',
        f'◆ STRENGTH: {result.get("setup_strength", 0)}/100',
        f'📡 MARKET  : {result.get("trend", "NEUTRAL")}',
    ]
    if result.get('rsi') is not None:
        lines.append(f'◈ MOMENTUM : {result["rsi"]}')
    if result.get('entry') is not None:
        lines.append(f'▶ ENTRY   : {result["entry"]}')
    for index, target in enumerate((result.get('tp') or [])[:3], start=1):
        lines.append(f'◆ TP{index}     : {target}')
    if result.get('stop') is not None:
        lines.append(f'🔻 STOP    : {result["stop"]}')
    if result.get('risk_reward'):
        lines.append(f'◆ R:R     : {result["risk_reward"]}')

    lines.extend([
        '',
        f'◈ SAMPLES  : {result.get("samples", 0)}',
        f'● STATE    : {result.get("reason", "UNKNOWN")}',
        '',
        'Precision is the only certainty.',
        'Education only. Execute with discipline.',
    ])
    return lines


def _format_signal(result: dict) -> str:
    return _terminal(_terminal_signal_lines(result))


def _main_menu_text() -> str:
    return _terminal([
        '[ ◉ SYSTEM STATE ]',
        '',
        '🟢 STATUS     : OPERATIONAL',
        '🟢 SENSORS    : ACTIVE',
        '🔐 CLEARANCE  : PENDING VERIFICATION',
        '',
        'Select a module to initialize data stream.',
        '',
        '📡 LIVE MARKET FEED',
        '⚡ NEURAL SIGNAL',
        '📊 MARKET ANALYSIS',
        '⚙️ SYSTEM SETTING',
    ])


def _system_info_text(access_active: bool) -> str:
    access_status = '🟢 PREMIUM ACTIVE' if access_active else '🔴 UNVERIFIED'
    channel_status = '🟢 VERIFIED' if access_active else '🔴 REQUIRED'
    role = 'PREMIUM MEMBER' if access_active else 'MEMBER ACCESS REQUIRED'
    return _terminal([
        '[ ⚙️ SYSTEM DIAGNOSTICS ]',
        '',
        '[ CORE STATUS ]',
        '🟢 STATUS         : ONLINE',
        '◆ SERVICE        : NEURAL GOLD v3.2',
        '◈ ASSET          : XAU/USD',
        '⏱ TIME FRAME     : M5',
        '',
        '[ 🔐 ACCESS ]',
        f'ACCESS LEVEL     : {access_status}',
        f'CHANNEL STATUS   : {channel_status}',
        '',
        '[ 👤 MEMBERSHIP ]',
        f'ROLE             : {role}',
        'SOURCE           : WHOP MEMBERSHIP',
        '',
        '[ 📡 MODULES ]',
        '📡 LIVE MARKET FEED : Real-time market pricing.',
        '⚡ NEURAL SIGNAL     : Algorithmic signal reads.',
        '📊 MARKET ANALYSIS  : Institutional market structure.',
        '',
        'Risk Warning: Volatility is absolute.',
    ])

BONUS_TEXT = _system_info_text(False)

ACCESS_INACTIVE_TEXT = _terminal([
    '[ 🔐 ACCESS CONTROL ]',
    '',
    '🔴 STATUS  : INACTIVE',
    '🔴 MEMBERSHIP : NOT VERIFIED',
    '',
    'Premium Channel membership is required.',
    'Join the Premium Channel through Whop,',
    'then return here to verify member access.',
])

ACCESS_ACTIVE_TEXT = _terminal([
    '[ 🔐 ACCESS CONTROL ]',
    '',
    '🟢 STATUS  : ACTIVE',
    '🟢 MEMBERSHIP : VERIFIED',
    '👤 ROLE    : PREMIUM MEMBER',
    '',
    'Membership verified successfully.',
    'All neural modules are now online.',
])

UNKNOWN_INPUT_TEXT = _terminal([
    '[ ⚠️ INPUT ERROR ]',
    '',
    "I didn't recognize that input.",
    '',
    'Use the four terminal views below.',
    '',
    '📡 LIVE MARKET FEED',
    '⚡ NEURAL SIGNAL',
    '📊 MARKET ANALYSIS',
    '⚙️ SYSTEM SETTING',
])

ERROR_TEXT = _terminal([
    '[ 🔴 SYSTEM FAULT ]',
    '',
    'A temporary error occurred.',
    '',
    'Your request was not completed.',
    'Please try again.',
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
    user_id = update.effective_user.id
    await asyncio.to_thread(database.ensure_user, user_id)
    access_active = await access.activate_member(context.bot, user_id)
    text = _system_info_text(access_active)
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=main_menu())


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
