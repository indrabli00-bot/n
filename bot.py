from __future__ import annotations

import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

import access
import database
import signal_engine
from config import TELEGRAM_BOT_TOKEN

log = logging.getLogger('bot')

TERMINAL_WIDTH = 34
DISCLAIMER = 'Market information & education only. Not personal financial advice. Trading involves risk.'


def _terminal(lines: list[str]) -> str:
    """Render every bot panel in one predictable monospace terminal width."""
    body = []
    for line in lines:
        text = str(line).replace('<', '&lt;').replace('>', '&gt;')
        if len(text) <= TERMINAL_WIDTH:
            body.append(text)
            continue
        words = text.split()
        current = ''
        for word in words:
            candidate = word if not current else f'{current} {word}'
            if len(candidate) <= TERMINAL_WIDTH:
                current = candidate
            else:
                if current:
                    body.append(current)
                current = word
        if current:
            body.append(current)
    return '<pre>' + '\n'.join(body) + '</pre>'


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

    targets = result.get('tp') or []
    for index, target in enumerate(targets[:3], start=1):
        lines.append(f'TP{index:<5}: {target}')
    if result.get('stop') is not None:
        lines.append(f'STOP   : {result["stop"]}')
    if result.get('risk_reward'):
        lines.append(f'R:R    : {result["risk_reward"]}')

    lines.extend(
        [
            f'DATA   : {result.get("samples", 0)} samples',
            f'STATE  : {result.get("reason", "UNKNOWN")}',
            '',
            'Setup strength bukan probabilitas',
            'kemenangan dan tidak menjamin hasil.',
            'Education only. Trade at your risk.',
        ]
    )
    return lines


def _format_signal(result: dict) -> str:
    return _terminal(_terminal_signal_lines(result))


def _main_menu_text() -> str:
    return _terminal(
        [
            '[ NEURAL GOLD ]',
            'XAU/USD MARKET INTELLIGENCE',
            '',
            'STATUS : ONLINE',
            'BOT    : MEMBER BONUS',
            '',
            'Premium Channel is the primary',
            'Neural Gold product. This bot is',
            'a bonus utility for channel members.',
        ]
    )


HELP_TEXT = _terminal(
    [
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
    ]
)

BONUS_TEXT = _terminal(
    [
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
    ]
)

ACCESS_INACTIVE_TEXT = _terminal(
    [
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
    ]
)

ACCESS_ACTIVE_TEXT = _terminal(
    [
        '[ BOT BONUS / ACTIVE ]',
        '',
        'CHANNEL : MEMBER',
        'BOT     : BONUS ACTIVE',
        '',
        'Your Premium Channel membership is',
        'confirmed by Telegram.',
        '',
        'Member-only bot features are active.',
    ]
)


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton('📡 SINYAL TERBARU', callback_data='signal'),
                InlineKeyboardButton('📊 STATUS AKSES', callback_data='status'),
            ],
            [
                InlineKeyboardButton('🎁 BONUS BOT', callback_data='bonus'),
                InlineKeyboardButton('ℹ️ CARA KERJA', callback_data='help'),
            ],
        ]
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.to_thread(database.ensure_user, update.effective_user.id)
    await update.message.reply_text(
        _main_menu_text(), parse_mode='HTML', reply_markup=main_menu()
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        HELP_TEXT, parse_mode='HTML', reply_markup=main_menu()
    )


async def premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        BONUS_TEXT, parse_mode='HTML', reply_markup=main_menu()
    )


async def _status_text(uid: int, bot) -> tuple[str, InlineKeyboardMarkup]:
    if not await access.has_access(bot, uid):
        return ACCESS_INACTIVE_TEXT, main_menu()
    return ACCESS_ACTIVE_TEXT, main_menu()


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, markup = await _status_text(update.effective_user.id, context.bot)
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=markup)


async def signal_text() -> str:
    samples = await asyncio.to_thread(database.recent_samples)
    return _format_signal(signal_engine.analyze(samples))


async def _send_signal(target, uid: int, bot) -> None:
    if not await access.has_access(bot, uid):
        if hasattr(target, 'edit_message_text'):
            await target.edit_message_text(
                ACCESS_INACTIVE_TEXT,
                parse_mode='HTML',
                reply_markup=main_menu(),
            )
        else:
            await target.reply_text(
                ACCESS_INACTIVE_TEXT,
                parse_mode='HTML',
                reply_markup=main_menu(),
            )
        return

    text = await signal_text()
    if hasattr(target, 'edit_message_text'):
        await target.edit_message_text(text, parse_mode='HTML', reply_markup=main_menu())
    else:
        await target.reply_text(text, parse_mode='HTML', reply_markup=main_menu())


async def signal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_signal(update.message, update.effective_user.id, context.bot)


async def link_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        BONUS_TEXT, parse_mode='HTML', reply_markup=main_menu()
    )


async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'home':
        await query.edit_message_text(
            _main_menu_text(), parse_mode='HTML', reply_markup=main_menu()
        )
        return
    if query.data == 'help':
        await query.edit_message_text(
            HELP_TEXT, parse_mode='HTML', reply_markup=main_menu()
        )
        return
    if query.data == 'bonus':
        await query.edit_message_text(
            BONUS_TEXT, parse_mode='HTML', reply_markup=main_menu()
        )
        return
    if query.data == 'status':
        text, markup = await _status_text(query.from_user.id, context.bot)
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=markup)
        return
    if query.data == 'signal':
        await _send_signal(query, query.from_user.id, context.bot)


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
    app.add_handler(CallbackQueryHandler(callbacks))
    return app
