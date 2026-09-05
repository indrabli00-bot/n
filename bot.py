from __future__ import annotations

import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

import access
import database
import signal_engine
import whop
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
            'ACCESS : CHECK REQUIRED',
            '',
            'Select an action below.',
        ]
    )


HELP_TEXT = _terminal(
    [
        '[ NEURAL GOLD / HOW IT WORKS ]',
        '',
        '01 DATA    : XAU/USD collected',
        '02 ENGINE  : trend / momentum /',
        '             volatility / structure',
        '03 SIGNAL  : LONG / SHORT / HOLD',
        '04 PUBLISH : qualifying signals',
        '             go to Premium Channel',
        '05 ACCESS  : Whop + Telegram',
        '             membership required',
        '',
        '[ STATUS ]',
        'LONG      : bullish',
        'SHORT     : bearish',
        'HOLD      : setup not confirmed',
        'DATA GAP  : insufficient data',
        '',
        '[ NOTE ]',
        'Setup strength is not a win',
        'probability and is not a guarantee.',
        '',
        'Education only. Trading involves risk.',
    ]
)

ACTIVATION_TEXT = _terminal(
    [
        '[ NEURAL GOLD / ACTIVATION ]',
        '',
        'PAYMENT  : WHOP',
        'BOT      : NO PAYMENT PROCESSING',
        '',
        '01 Subscribe to Neural Gold on Whop.',
        '02 Connect your Whop account below.',
        '03 Ensure membership is ACTIVE and',
        '   you joined the Premium Channel.',
        '04 Access requires both checks.',
        '',
        'After linking, Whop login is not',
        'required again for normal bot use.',
    ]
)

ACCESS_INACTIVE_TEXT = _terminal(
    [
        '[ ACCESS / INACTIVE ]',
        '',
        'WHOP       : CHECK REQUIRED',
        'TELEGRAM   : CHECK REQUIRED',
        '',
        'Activate your Whop membership,',
        'connect the account, and join the',
        'Premium Channel.',
    ]
)

PREMIUM_REQUIRED_TEXT = _terminal(
    [
        '[ PREMIUM ACCESS REQUIRED ]',
        '',
        'Connect your Whop account and',
        'ensure membership + Premium',
        'Channel access are ACTIVE.',
    ]
)


def access_active_text(expiry: str) -> str:
    return _terminal(
        [
            '[ ACCESS / ACTIVE ]',
            '',
            'WHOP MEMBERSHIP : ACTIVE',
            f'RENEWAL END     : {expiry}',
            '',
            'Premium bot access is active.',
        ]
    )


async def activation_menu(telegram_id: int) -> InlineKeyboardMarkup:
    link_url = await whop.create_link_url(telegram_id)
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton('🔗 HUBUNGKAN WHOP', url=link_url)],
            [InlineKeyboardButton('⬅️ MENU', callback_data='home')],
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
                InlineKeyboardButton('🔗 HUBUNGKAN WHOP', callback_data='premium'),
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


async def _send_activation(target, telegram_id: int, *, edit: bool = False) -> None:
    markup = await activation_menu(telegram_id)
    if edit:
        await target.edit_message_text(
            ACTIVATION_TEXT, parse_mode='HTML', reply_markup=markup
        )
    else:
        await target.reply_text(
            ACTIVATION_TEXT, parse_mode='HTML', reply_markup=markup
        )


async def premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await _send_activation(update.message, update.effective_user.id)
    except Exception:
        log.exception('activation menu failed')
        await update.message.reply_text(
            _terminal(
                [
                    '[ ACTIVATION / ERROR ]',
                    '',
                    'Activation menu is temporarily',
                    'unavailable. Please try again.',
                ]
            ),
            parse_mode='HTML',
        )


async def _status_text(uid: int, bot) -> tuple[str, InlineKeyboardMarkup]:
    if not await access.has_access(bot, uid):
        return ACCESS_INACTIVE_TEXT, await activation_menu(uid)

    membership = await asyncio.to_thread(database.get_membership_for_telegram, uid)
    expiry = (
        membership.renewal_period_end.isoformat()
        if membership and membership.renewal_period_end
        else '-'
    )
    return access_active_text(expiry), main_menu()


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
                PREMIUM_REQUIRED_TEXT,
                parse_mode='HTML',
                reply_markup=await activation_menu(uid),
            )
        else:
            await target.reply_text(
                PREMIUM_REQUIRED_TEXT,
                parse_mode='HTML',
                reply_markup=await activation_menu(uid),
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
    try:
        await _send_activation(update.message, update.effective_user.id)
    except Exception:
        log.exception('activation link failed')
        await update.message.reply_text(
            _terminal(
                [
                    '[ ACTIVATION / ERROR ]',
                    '',
                    'Activation menu is temporarily',
                    'unavailable. Please try again.',
                ]
            ),
            parse_mode='HTML',
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
    if query.data == 'premium':
        try:
            await _send_activation(query, query.from_user.id, edit=True)
        except Exception:
            log.exception('callback activation failed')
            await query.edit_message_text(
                _terminal(
                    [
                        '[ ACTIVATION / ERROR ]',
                        '',
                        'Activation menu is temporarily',
                        'unavailable. Please try again.',
                    ]
                ),
                parse_mode='HTML',
                reply_markup=main_menu(),
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
