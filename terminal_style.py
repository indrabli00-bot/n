"""NEURAL GOLD v3.2 — Phase 0.0 TERMINAL INTELLIGENCE WRAPPER.

Central aesthetic layer for every user-facing bot response:
  - [ SYSTEM ] / [ STATUS ] / [ ACCESS ]              -> INITIALIZATION / WELCOME
  - [ ANALYSIS ] / [ CORE ] / [ EXTRACTING ] / [ NEURAL-MAP ] -> processing prefixes
  - [ !!! INTELLIGENCE REPORT : XAUUSD !!! ]          -> signal result header
  - [ ERROR ]: DATA_GAP_DETECTED / [ FAULT ]: LINK_TIMEOUT // RETRYING... -> failures
  - monospaced <pre> panels, UTC stamps, restricted-data footer

Phase 0.0 CORE RULES enforced by construction:
  - Zero Fluff: no greetings, no corporate filler.
  - Preservation: established Neural Gold technical/feature terms are wrapped,
    never rewritten (wrappers live here; product strings stay where they are).
  - ACTION routes use the centralized i18n catalog for customer-facing copy.
"""
from __future__ import annotations

from datetime import datetime, timezone

from config import NEURAL_VERSION
from i18n import t


# ---------------------------------------------------------------------------
# Core terminal primitives
# ---------------------------------------------------------------------------


def stamp() -> str:
    """UTC timestamp for terminal aesthetics."""
    return datetime.now(timezone.utc).strftime("[ %Y-%m-%d %H:%M:%S UTC ]")


def line(tag: str, msg: str) -> str:
    """One [ TAG ]: MESSAGE terminal line."""
    return f"[ {tag} ]: {msg}"


def panel(rows, escape: bool = False) -> str:
    """Monospaced terminal panel. Set escape=True for raw (unescaped) rows."""
    if escape:
        import html as _html
        rows = [_html.escape(str(r)) for r in rows]
    return "<pre>" + "\n".join(rows) + "</pre>"


# ── Standard panel geometry: ONE width everywhere, fits small screens.
PANEL_W = 36   # total visual width including borders
INNER_W = 34   # usable inner width for content rows


def prow(text: str, inner: int = INNER_W) -> str:
    """Pad (or hard-trim) a panel row to the standard inner width."""
    s = str(text)
    return s[:inner] if len(s) > inner else s.ljust(inner)


def bar(ch: str = "─", inner: int = INNER_W) -> str:
    """Horizontal rule of the standard inner width."""
    return ch * inner


def boot(granted: bool) -> str:
    """Spec A — INITIALIZATION/WELCOME boot sequence."""
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
    """Spec C — trading signal result header."""
    return "[ !!! INTELLIGENCE REPORT : XAUUSD !!! ]"


def intel_footer() -> str:
    """Spec C — restricted-data footer."""
    return line("SECURITY", "Restricted Data. For Operator Eyes Only.")


def data_gap(hint: str | None = None) -> str:
    """Spec D — generic data-gap error."""
    text = line("ERROR", "DATA_GAP_DETECTED")
    return f"{text}\n{hint}" if hint else text


def link_timeout(hint: str | None = None) -> str:
    """Spec D — upstream failure error."""
    text = line("FAULT", "LINK_TIMEOUT // RETRYING...")
    return f"{text}\n{hint}" if hint else text


# ---------------------------------------------------------------------------
# Localized action guidance
# ---------------------------------------------------------------------------


def _guide(lang: str, keys: tuple[str, ...], tag: str) -> str:
    """Build action guidance exclusively from the centralized i18n catalog."""
    body = "\n".join(
        f"{i}. {t(lang, key)}" for i, key in enumerate(keys, 1)
    )
    return f"{line(tag, t(lang, 'select_plan'))}\n{body}"


def buy_guide(lang: str, tag: str = "PAYMENT") -> str:
    """Condensed purchase guide using only centralized localized strings."""
    return _guide(
        lang,
        ("select_plan", "use_package_buttons", "paid"),
        tag,
    )


def pay_guide(lang: str, tag: str = "PAYMENT") -> str:
    """Full purchase + activation guide using only centralized localized strings."""
    return _guide(
        lang,
        (
            "select_plan",
            "use_package_buttons",
            "paid",
            "verified_auto",
            "activate",
        ),
        tag,
    )
