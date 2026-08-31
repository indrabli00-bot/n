"""NEURAL GOLD v3.2 — terminal UI helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from config import NEURAL_VERSION
from i18n import t

PANEL_W = 36
INNER_W = 34


def stamp() -> str:
    """UTC timestamp for terminal aesthetics."""
    return datetime.now(timezone.utc).strftime("[ %Y-%m-%d %H:%M:%S UTC ]")


def line(tag: str, msg: str) -> str:
    """One [ TAG ]: MESSAGE terminal line."""
    return f"[ {tag} ]: {msg}"


def word_wrap(text: str, max_width: int) -> list[str]:
    """Word-wrap with character-break fallback for tokens longer than max_width."""
    if max_width <= 0:
        raise ValueError("max_width must be positive")
    if len(text) <= max_width:
        return [text]

    words = text.split()
    lines: list[str] = []
    current = ""

    for word in words:
        if len(word) > max_width:
            if current:
                lines.append(current.rstrip())
                current = ""
            for i in range(0, len(word), max_width):
                lines.append(word[i:i + max_width])
            continue

        candidate = f"{current} {word}" if current else word
        if len(candidate) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current.rstrip())
            current = word

    if current:
        lines.append(current.rstrip())

    return lines if lines else [""]


def render_header(user, lang: str) -> str:
    """Render the canonical 3-line operator header plus trailing blank line."""
    timestamp = stamp()
    operator_name = user.first_name or "OPERATOR"
    import auth
    import database

    is_active, _ = auth.verify_token(user.id)
    if is_active:
        db_user = database.get_user_by_telegram_id(user.id)
        expiry = database.normalize_datetime_utc(db_user.subscription_expiry) if db_user else None
        if expiry:
            days_left = (expiry - datetime.now(timezone.utc)).days
            status_text = f"{t(lang, 'active')} 🟢 ({t(lang, 'days_remaining')}: {days_left} {t(lang, 'days')})"
        else:
            status_text = f"{t(lang, 'active')} 🟢"
    else:
        status_text = f"{t(lang, 'inactive')} 🔴"

    return f"{timestamp}\nOPERATOR : {operator_name}\nSTATUS   : {status_text}\n"


def render_terminal_box(content: str) -> str:
    """Render a fixed 36-character box with 34-character wrapped content."""
    normalized: list[str] = []
    for raw_line in content.split("\n"):
        for wrapped in word_wrap(raw_line, INNER_W):
            normalized.append(f"│{wrapped.ljust(INNER_W)}│")

    top = f"┍{'━' * INNER_W}┑"
    bottom = f"┕{'━' * INNER_W}┙"
    return f"{top}\n" + "\n".join(normalized) + f"\n{bottom}"


def render_persistent_nav(lang: str):
    """Return the canonical persistent two-button navigation row."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"🏠 {t(lang, 'menu')}", callback_data="nav:home"),
            InlineKeyboardButton(f"👨‍💼 {t(lang, 'account')}", callback_data="screen:account"),
        ]
    ])


def panel(rows: Iterable[str], escape: bool = False) -> str:
    """Legacy monospace panel retained for existing callers; uses fixed geometry."""
    if escape:
        import html as _html
        rows = [_html.escape(str(r)) for r in rows]
    return "<pre>" + "\n".join(str(r).ljust(INNER_W)[:INNER_W] for r in rows) + "</pre>"


def prow(text: str, inner: int = INNER_W) -> str:
    s = str(text)
    return s[:inner] if len(s) > inner else s.ljust(inner)


def bar(ch: str = "─", inner: int = INNER_W) -> str:
    return ch * inner


def boot(granted: bool) -> str:
    seq = [
        line("SYSTEM", f"INITIALIZING NEURAL GOLD {NEURAL_VERSION}..."),
        line("STATUS", "SYNCING GLOBAL BULLION RESERVES..."),
    ]
    seq.append(
        line("ACCESS", "GRANTED. WELCOME, OPERATOR.")
        if granted
        else line("ACCESS", "PENDING // CLEARANCE REQUIRED")
    )
    return "\n".join(seq)


def intel_header() -> str:
    return "[ !!! INTELLIGENCE REPORT : XAUUSD !!! ]"


def intel_footer() -> str:
    return line("SECURITY", "Restricted Data. For Operator Eyes Only.")


def data_gap(hint: str | None = None) -> str:
    text = line("ERROR", "DATA_GAP_DETECTED")
    return f"{text}\n{hint}" if hint else text


def link_timeout(hint: str | None = None) -> str:
    text = line("FAULT", "LINK_TIMEOUT // RETRYING...")
    return f"{text}\n{hint}" if hint else text


def _guide(lang: str, keys: tuple[str, ...], tag: str) -> str:
    body = "\n".join(f"{i}. {t(lang, key)}" for i, key in enumerate(keys, 1))
    return f"{line(tag, t(lang, 'select_plan'))}\n{body}"


def buy_guide(lang: str, tag: str = "PAYMENT") -> str:
    return _guide(lang, ("select_plan", "use_package_buttons", "paid"), tag)


def pay_guide(lang: str, tag: str = "PAYMENT") -> str:
    return _guide(lang, ("select_plan", "use_package_buttons", "paid", "verified_auto", "activate"), tag)
