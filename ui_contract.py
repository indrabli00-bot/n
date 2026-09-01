"""Canonical Neural Gold v3.2 customer UI contract.

This module owns customer-screen presentation and is installed by app.py before
Belmo builds the Telegram application. Legacy admin/token handlers remain in
main.py; this module replaces only customer navigation/rendering.
"""
from __future__ import annotations

import asyncio
import html
from datetime import datetime, timezone
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update

import api_handler
import auth
import database
import terminal_style as ts
import whop_storage
from config import ADMIN_TELEGRAM_ID
from i18n import LANGUAGES, detect_language, language_buttons, t

MODULES = {
    "price": "MARKET PULSE",
    "signal": "NEURAL STRIKES",
    "analysis": "STRUCTURE MAP",
}


def _lang(update: Update) -> str:
    user = update.effective_user
    return database.get_user_language(user.id) if user else "en"


def _active(update: Update) -> bool:
    user = update.effective_user
    return bool(user and auth.verify_token(user.id)[0])


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _money(value: float) -> str:
    return f"{value:,.2f}"


def _nav(update: Update) -> list[list[InlineKeyboardButton]]:
    lang = _lang(update)
    return [[
        InlineKeyboardButton(f"🏠 {t(lang, 'menu')}", callback_data="nav:home"),
        InlineKeyboardButton(f"👨‍💼 {t(lang, 'account')}", callback_data="screen:account"),
    ]]


def _keyboard(update: Update, rows: list[list[InlineKeyboardButton]] | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(list(rows or []) + _nav(update))


def _header(update: Update, screen: str) -> str:
    user = update.effective_user
    active = _active(update)
    operator = (f"@{user.username}" if user and user.username else (user.first_name if user else "OPERATOR"))
    status = "ACTIVE" if active else "INACTIVE"
    return f"NEURAL GOLD v3.2 / {ts.stamp()} / {screen}\nOPERATOR: {_esc(operator)}\nSTATUS: {status}"


def _screen(update: Update, screen: str, terminal: str, subtitle: str, keyboard: InlineKeyboardMarkup) -> tuple[str, InlineKeyboardMarkup]:
    body = ts.render_terminal_box(terminal, max_width=70)
    return f"{_header(update, screen)}\n\n<pre>{body}</pre>\n\n&gt;&gt; {subtitle}", keyboard


async def _present(update: Update, text: str, keyboard: InlineKeyboardMarkup, edit: bool = True) -> None:
    query = update.callback_query
    if query and edit:
        try:
            await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=keyboard)
            return
        except Exception as exc:
            if "not modified" in str(exc).lower():
                return
    if query and query.message:
        try:
            await query.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
            return
        except Exception:
            pass
    if update.message:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)


def _module_rows(update: Update, refresh: str | None = None) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = []
    if refresh:
        rows.append([InlineKeyboardButton(t(_lang(update), "refresh"), callback_data=f"refresh:{refresh}")])
    rows.extend([
        [InlineKeyboardButton("MARKET PULSE", callback_data="screen:price"), InlineKeyboardButton("NEURAL STRIKES", callback_data="screen:signal")],
        [InlineKeyboardButton("STRUCTURE MAP", callback_data="screen:analysis")],
    ])
    return rows


def _locked_module_rows(update: Update) -> list[list[InlineKeyboardButton]]:
    return [
        [InlineKeyboardButton("🔒 MARKET PULSE", callback_data="screen:price"), InlineKeyboardButton("🔒 NEURAL STRIKES", callback_data="screen:signal")],
        [InlineKeyboardButton("🔒 STRUCTURE MAP", callback_data="screen:analysis")],
        [InlineKeyboardButton(f"💎 {t(_lang(update), 'activate_premium')}", callback_data="screen:activate")],
    ]


def _access_keyboard(update: Update, module: str | None = None) -> InlineKeyboardMarkup:
    import phase2_bot
    tid = update.effective_user.id
    rows = [[
        InlineKeyboardButton(f"🟢 {t(_lang(update), 'days7')}", url=phase2_bot.checkout_link(tid, 7)),
        InlineKeyboardButton(f"🟡 {t(_lang(update), 'days14')}", url=phase2_bot.checkout_link(tid, 14)),
    ], [InlineKeyboardButton(f"🔵 {t(_lang(update), 'days30')}", url=phase2_bot.checkout_link(tid, 30))]]
    return _keyboard(update, rows)


async def render_home(update: Update, context, edit: bool = True) -> None:
    active = _active(update)
    terminal = "\n".join([
        "[ SYSTEM ]: INITIALIZING...",
        "[ STATUS ]: SYNCING GLOBAL BULLION RESERVES...",
        "[ ACCESS ]: GRANTED // WELCOME OPERATOR" if active else "[ ACCESS ]: PENDING // CLEARANCE REQUIRED",
    ])
    rows = _module_rows(update) if active else _locked_module_rows(update)
    text, keyboard = _screen(update, "Home", terminal, "HOME // Select module", _keyboard(update, rows))
    await _present(update, text, keyboard, edit=edit)


async def render_menu(update: Update, context) -> None:
    rows = [
        [InlineKeyboardButton("MARKET PULSE", callback_data="screen:price"), InlineKeyboardButton("NEURAL STRIKES", callback_data="screen:signal")],
        [InlineKeyboardButton("STRUCTURE MAP", callback_data="screen:analysis")],
        [InlineKeyboardButton(f"🌐 {t(_lang(update), 'language')}", callback_data="settings:language")],
        [InlineKeyboardButton(f"❓ {t(_lang(update), 'support')}", callback_data="screen:help")],
    ]
    terminal = "[ SYSTEM ]: NAVIGATION ONLINE\n[ MODE ]: CUSTOMER CONTROL"
    text, keyboard = _screen(update, "Menu", terminal, "MENU // Navigation", _keyboard(update, rows))
    await _present(update, text, keyboard)


async def render_language(update: Update, context) -> None:
    rows = [[InlineKeyboardButton(label, callback_data=data)] for label, data in language_buttons()]
    terminal = "[ LANGUAGE ]: SELECT INTERFACE LANGUAGE\n[ AVAILABLE ]: ENGLISH / BAHASA INDONESIA"
    text, keyboard = _screen(update, "Language", terminal, "LANGUAGE // Select language", _keyboard(update, rows))
    await _present(update, text, keyboard)


async def render_help(update: Update, context) -> None:
    body = t(_lang(update), "help_body")
    text, keyboard = _screen(update, "Help", body, "HELP // Support", _keyboard(update, [[InlineKeyboardButton(t(_lang(update), "contact"), url=f"tg://user?id={ADMIN_TELEGRAM_ID}")]] if ADMIN_TELEGRAM_ID else []))
    await _present(update, text, keyboard)


async def render_account(update: Update, context) -> None:
    user = update.effective_user
    if not user:
        return
    db_user = database.get_user_by_telegram_id(user.id)
    active = _active(update)
    if active and db_user:
        expiry = database.normalize_datetime_utc(db_user.subscription_expiry)
        expiry_text = expiry.strftime("%d %b %Y • %H:%M UTC") if expiry else "—"
        days_left = max(0, (expiry - datetime.now(timezone.utc)).days) if expiry else 0
        terminal = "\n".join(["[ OPERATOR HUB ]", f"TELEGRAM_ID : {user.id}", "CLEARANCE   : PREMIUM ACTIVE", f"EXPIRY      : {expiry_text}", f"DAYS LEFT   : {days_left}"])
        rows = [[InlineKeyboardButton(f"🔄 {t(_lang(update), 'renew')}", callback_data="screen:renew")], [InlineKeyboardButton(f"📊 {t(_lang(update), 'history')}", callback_data="screen:history")]]
    else:
        terminal = "\n".join(["[ OPERATOR HUB ]", f"TELEGRAM_ID : {user.id}", "CLEARANCE   : INACTIVE", "SUBSCRIPTION: NONE"])
        rows = _locked_module_rows(update)
    text, keyboard = _screen(update, "Account", terminal, "ACCOUNT // " + ("Active subscription" if active else "Inactive subscription"), _keyboard(update, rows))
    await _present(update, text, keyboard)


async def render_history(update: Update, context) -> None:
    user = update.effective_user
    if not user:
        return
    rows = ["[ TRANSACTION HISTORY ]"]
    try:
        orders = whop_storage.recent_orders_for(user.id, 5)
    except Exception:
        orders = []
    if orders:
        for order in orders:
            rows.extend([f"ID       : {_esc(str(order.get('id', '—'))[:20])}", f"STATUS   : {_esc(str(order.get('status', '—')).upper())}", f"DURATION : {order.get('duration_days', '—')} days", ""])
    else:
        rows.append("NO TRANSACTIONS")
    text, keyboard = _screen(update, "Account", "\n".join(rows).rstrip(), "ACCOUNT // Transaction history", _keyboard(update))
    await _present(update, text, keyboard)


async def render_access(update: Update, context, module: str | None = None) -> None:
    module_label = MODULES.get(module or "", "PREMIUM ACCESS")
    terminal = f"[ ACCESS ]: PREMIUM PACKAGE SELECTION\n[ MODULE ]: {module_label}\n\n[ PLAN ]: 7D / 14D / 30D"
    text, keyboard = _screen(update, module_label if module else "Premium Access", terminal, "SELECT ACCESS // 7D / 14D / 30D", _access_keyboard(update, module))
    await _present(update, text, keyboard)


async def render_price(update: Update, context) -> None:
    if not _active(update):
        await render_access(update, context, "price")
        return
    user = update.effective_user
    try:
        data = await asyncio.wait_for(api_handler.get_cached_or_fresh_price(user.id), timeout=10.0)
        bid, ask = float(data["bid"]), float(data["ask"])
        mid = (bid + ask) / 2
        terminal = "\n".join(["[ MARKET PULSE ]", f"PRICE : {_money(mid)}", f"BID   : {_money(bid)}", f"ASK   : {_money(ask)}", f"HIGH  : {_money(float(data['high']))}", f"LOW   : {_money(float(data['low']))}", f"SOURCE: {_esc(data.get('source', '—'))}"])
    except Exception:
        terminal = "[ MARKET PULSE ]\n[ ERROR ]: DATA TEMPORARILY UNAVAILABLE\n>> REFRESH TO RETRY"
    text, keyboard = _screen(update, "MARKET PULSE", terminal, "MARKET PULSE // XAU/USD", _keyboard(update, _module_rows(update, "price")))
    await _present(update, text, keyboard)


async def render_signal(update: Update, context) -> None:
    if not _active(update):
        await render_access(update, context, "signal")
        return
    user = update.effective_user
    try:
        data = await asyncio.wait_for(api_handler.get_cached_or_fresh_price(user.id), timeout=10.0)
        indicators = api_handler._simulate_technical_indicators(float(data["bid"]), float(data.get("change_percent", 0)))
        signal = api_handler._determine_signal(float(data["bid"]), indicators)
        terminal = "\n".join(["[ NEURAL STRIKES ]", f"SIGNAL : {signal['direction']}", f"ENTRY  : {_money(signal['entry_low'])} - {_money(signal['entry_high'])}", f"TP1    : {_money(signal['tp1']) if signal['tp1'] else '—'}", f"TP2    : {_money(signal['tp2']) if signal['tp2'] else '—'}", f"TP3    : {_money(signal['tp3']) if signal['tp3'] else '—'}", f"STOP   : {_money(signal['sl']) if signal['sl'] else '—'}"])
    except Exception:
        terminal = "[ NEURAL STRIKES ]\n[ ERROR ]: SIGNAL TEMPORARILY UNAVAILABLE\n>> REFRESH TO RETRY"
    text, keyboard = _screen(update, "NEURAL STRIKES", terminal, "NEURAL STRIKES // XAU/USD", _keyboard(update, _module_rows(update, "signal")))
    await _present(update, text, keyboard)


async def render_analysis(update: Update, context) -> None:
    if not _active(update):
        await render_access(update, context, "analysis")
        return
    user = update.effective_user
    try:
        data = await asyncio.wait_for(api_handler.get_cached_or_fresh_price(user.id), timeout=10.0)
        indicators = api_handler._simulate_technical_indicators(float(data["bid"]), float(data.get("change_percent", 0)))
        terminal = "\n".join(["[ STRUCTURE MAP ]", f"TREND : {_esc(str(indicators.get('ema_trend', 'NEUTRAL')).upper())}", f"RSI   : {indicators.get('rsi', '—')}", f"MACD  : {indicators.get('macd_hist', '—')}", f"EMA   : {indicators.get('ema', '—')}", f"ATR   : {indicators.get('atr', '—')}"])
    except Exception:
        terminal = "[ STRUCTURE MAP ]\n[ ERROR ]: STRUCTURE DATA TEMPORARILY UNAVAILABLE\n>> REFRESH TO RETRY"
    text, keyboard = _screen(update, "STRUCTURE MAP", terminal, "STRUCTURE MAP // XAU/USD", _keyboard(update, _module_rows(update, "analysis")))
    await _present(update, text, keyboard)


async def render_activate(update: Update, context) -> None:
    await render_access(update, context)


async def render_renew(update: Update, context) -> None:
    await render_access(update, context)


async def _start(update: Update, context) -> None:
    user = update.effective_user
    if not user:
        return
    try:
        existing = database.get_user_by_telegram_id(user.id)
        if existing is None:
            database.create_user(user.id, user.username, user.first_name, detect_language(user.language_code))
    except Exception:
        pass
    await render_home(update, context, edit=False)


async def callback_router(update: Update, context) -> None:
    query = update.callback_query
    if not query:
        return
    data = query.data or ""
    try:
        await query.answer()
    except Exception:
        pass
    if data in {"nav:home", "screen:home", "screen:menu"}:
        await render_menu(update, context)
        return
    if data == "screen:account":
        await render_account(update, context)
        return
    if data == "settings:language":
        await render_language(update, context)
        return
    if data.startswith("lang:"):
        lang = data.split(":", 1)[1]
        if lang not in LANGUAGES:
            lang = "en"
        database.set_user_language(query.from_user.id, lang)
        await render_menu(update, context)
        return
    routes = {
        "price": render_price,
        "signal": render_signal,
        "analysis": render_analysis,
        "activate": render_activate,
        "access": render_activate,
        "renew": render_renew,
        "history": render_history,
        "help": render_help,
    }
    if data.startswith("screen:"):
        target = data.split(":", 1)[1]
        if target in MODULES and not _active(update):
            await render_access(update, context, target)
            return
        handler = routes.get(target)
        if handler:
            await handler(update, context)
        return
    if data.startswith("refresh:"):
        target = data.split(":", 1)[1]
        handler = routes.get(target)
        if handler:
            await handler(update, context)
        return


def install(main_module) -> None:
    """Install the contract into the legacy main module before build_application."""
    main_module.render_home = render_home
    main_module.render_menu = render_menu
    main_module.render_account = render_account
    main_module.render_history = render_history
    main_module.render_price = render_price
    main_module.render_signal = render_signal
    main_module.render_analysis = render_analysis
    main_module.render_activate = render_activate
    main_module.render_access = render_access
    main_module.render_renew = render_renew
    main_module.render_help = render_help
    main_module.start_command = _start
    main_module.callback_router = callback_router
