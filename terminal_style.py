"""NEURAL GOLD v3.2 — terminal UI helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from config import NEURAL_VERSION
from i18n import t


# Group 3.3 canonical contract: responsive terminal content ceiling.
DEFAULT_MAX_WIDTH = 70


def stamp() -> str:
    """Return the canonical UTC timestamp."""
    return datetime.now(timezone.utc).strftime("[ %Y-%m-%d %H:%M:%S UTC ]")


def line(tag: str, msg: str) -> str:
    return f"[ {tag} ]: {msg}"


def word_wrap(text: str, max_width: int = DEFAULT_MAX_WIDTH) -> list[str]:
    """Wrap text by character count and split overlong tokens."""
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
    """Render the canonical plain-text five-line header."""
    import auth
    active, _ = auth.verify_token(user.id)
    status_key = "active" if active else "inactive"
    status_word = t(lang, status_key)
    status_word = status_word[:1].upper() + status_word[1:]
    status = f"{status_word} {'🟢' if active else '🔴'}"
    operator = user.first_name or "OPERATOR"
    return f"NEURAL GOLD {NEURAL_VERSION}\n{stamp()}\nOPERATOR : {operator}\nSTATUS   : {status}"


def _hold_diagnostics(content: str) -> list[str]:
    """Return actionable HOLD context from the latest live SMC result."""
    if "[ NEURAL STRIKES ]" not in content or "SIGNAL : HOLD" not in content:
        return []
    try:
        import api_handler
        signal = api_handler._latest_smc_signal or {}
        reasons = [str(x) for x in signal.get("reasons", []) if str(x).strip()]
        if not reasons:
            reasons = ["CONFIRMATION NOT DETECTED", "WAIT FOR A VALID M5 SETUP"]
        tf_bias = str(signal.get("tf_bias", "")).upper()
        if tf_bias == "DATA_GAP":
            status = "WAITING FOR LIVE DATA"
            action = "DO NOT ENTER // WAIT FOR LIVE 5M/15M DATA"
        else:
            status = "WAITING FOR CONFIRMATION"
            action = "DO NOT ENTER // WAIT FOR CONFIRMED M5 SETUP"
        return ["STATUS : " + status, "REASON : " + reasons[0], "ACTION : " + action]
    except Exception:
        return ["STATUS : WAITING FOR CONFIRMATION", "ACTION : DO NOT ENTER // WAIT FOR M5 CONFIRMATION"]


def render_terminal_box(content: str, max_width: int = DEFAULT_MAX_WIDTH) -> str:
    """Return terminal content and actionable HOLD diagnostics when applicable."""
    diagnostics = _hold_diagnostics(content)
    if diagnostics:
        content = content.rstrip() + "\n" + "\n".join(diagnostics)
    return "\n".join(
        part
        for raw_line in content.split("\n")
        for part in word_wrap(raw_line, max_width)
    )


def render_persistent_nav(lang: str):
    """Return the premium persistent navigation row with balanced labels."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"⌂  {t(lang, 'menu')}", callback_data="nav:home"),
        InlineKeyboardButton(f"◈  {t(lang, 'account')}", callback_data="screen:account"),
    ]])


def panel(rows: Iterable[str], escape: bool = False) -> str:
    """Legacy content helper; presentation ownership remains with main.py."""
    if escape:
        import html as _html
        rows = [_html.escape(str(r)) for r in rows]
    return "\n".join(str(r) for r in rows)


def prow(text: str, max_width: int = DEFAULT_MAX_WIDTH) -> str:
    return word_wrap(str(text), max_width)[0]


def bar(ch: str = "─", max_width: int = DEFAULT_MAX_WIDTH) -> str:
    """Return a legacy separator using the configured content ceiling."""
    return ch * max_width


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
