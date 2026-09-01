"""NEURAL GOLD v3.2 — terminal UI helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from config import NEURAL_VERSION
from i18n import t


def stamp() -> str:
    """Return the canonical UTC timestamp."""
    return datetime.now(timezone.utc).strftime("[ %Y-%m-%d %H:%M:%S UTC ]")


def line(tag: str, msg: str) -> str:
    return f"[ {tag} ]: {msg}"


def word_wrap(text: str, max_width: int | None = None) -> list[str]:
    """Wrap text only when an explicit maximum width is supplied."""
    if max_width is None:
        return [text]
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
            lines.extend(word[i:i + max_width] for i in range(0, len(word), max_width))
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
    return lines or [""]


def render_header(user, lang: str) -> str:
    """Render the canonical plain-text operator header."""
    import auth
    active, _ = auth.verify_token(user.id)
    status = f"{t(lang, 'active')} 🟢" if active else f"{t(lang, 'inactive')} 🔴"
    operator = user.first_name or "OPERATOR"
    return f"{stamp()}\nOPERATOR : {operator}\nSTATUS   : {status}"


def render_terminal_box(content: str, max_width: int | None = None) -> str:
    """Return preformatted content without a decorative border.

    Telegram does not expose the recipient viewport width to bots. Natural line
    width is therefore the default; callers may provide a maximum width when a
    specific application context requires wrapping.
    """
    return "\n".join(
        part
        for raw_line in content.split("\n")
        for part in word_wrap(raw_line, max_width)
    )


def render_persistent_nav(lang: str):
    """Return the canonical persistent two-button navigation row."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"🏠 {t(lang, 'menu')}", callback_data="nav:home"),
        InlineKeyboardButton(f"👨‍💼 {t(lang, 'account')}", callback_data="screen:account"),
    ]])


def panel(rows: Iterable[str], escape: bool = False) -> str:
    """Legacy content helper; presentation ownership remains with main.py."""
    if escape:
        import html as _html
        rows = [_html.escape(str(r)) for r in rows]
    return "\n".join(str(r) for r in rows)


def prow(text: str, max_width: int | None = None) -> str:
    return word_wrap(str(text), max_width)[0]


def bar(ch: str = "─", max_width: int | None = None) -> str:
    """Return an optional separator only when an explicit width is requested."""
    return "" if max_width is None else ch * max_width


def boot(granted: bool) -> str:
    seq = [
        line("SYSTEM", f"INITIALIZING NEURAL GOLD {NEURAL_VERSION}..."),
        line("STATUS", "SYNCING GLOBAL BULLION RESERVES..."),
        line("ACCESS", "GRANTED. WELCOME, OPERATOR.") if granted else line("ACCESS", "PENDING // CLEARANCE REQUIRED"),
    ]
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
