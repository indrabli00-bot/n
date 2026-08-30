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
  - Mixed register for ACTION routes (payment, activation): terminal frame +
    plain, simple, localized step-by-step guidance so every operator can
    actually follow the purchase flow.
"""
from __future__ import annotations

import html
from datetime import datetime, timezone

from config import NEURAL_VERSION

# ---------------------------------------------------------------------------
# Core terminal primitives
# ---------------------------------------------------------------------------


def stamp() -> str:
    """Fake-real-time UTC timestamp for terminal aesthetics."""
    return datetime.now(timezone.utc).strftime("[ %Y-%m-%d %H:%M:%S UTC ]")


def line(tag: str, msg: str) -> str:
    """One [ TAG ]: MESSAGE terminal line."""
    return f"[ {tag} ]: {msg}"


def panel(rows, escape: bool = False) -> str:
    """Monospaced terminal panel. Set escape=True for raw (unescaped) rows."""
    if escape:
        rows = [_html.escape(str(r)) for r in rows]
    return "<pre>" + "\n".join(rows) + "</pre>"


# ── Standard panel geometry (operator fix): ONE width everywhere, fits small screens.
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
# Mixed-register action guidance (terminal frame + plain localized steps)
# Payment/purchase routes must stay understandable for every operator.
# ---------------------------------------------------------------------------

_BUY_STEPS = {
    "en": [
        "Tap one of the package buttons below (7 / 14 / 30 days).",
        "Complete the payment on the Whop page that opens.",
        "Return here and tap \"\U0001F4B3 I HAVE PAID\".",
    ],
    "id": [
        "Ketuk salah satu tombol paket di bawah (7 / 14 / 30 hari).",
        "Selesaikan pembayaran di halaman Whop yang terbuka.",
        "Kembali ke bot ini, lalu ketuk \"\U0001F4B3 SAYA SUDAH MEMBAYAR\".",
    ],
    "vi": [
        "Nhấn một trong các nút gói bên dưới (7 / 14 / 30 ngày).",
        "Hoàn tất thanh toán trên trang Whop mở ra.",
        "Quay lại bot và nhấn \"\U0001F4B3 TÔI ĐÃ THANH TOÁN\".",
    ],
    "hi": [
        "नीचे दिए किसी भी पैकेज बटन को दबाएँ (7 / 14 / 30 दिन)।",
        "खुलने वाले Whop पेज पर भुगतान पूरा करें।",
        "वापस बॉट में आएँ और \"\U0001F4B3 मैंने भुगतान कर दिया है\" दबाएँ।",
    ],
    "zh": [
        "点击下方任一套餐按钮（7 / 14 / 30 天）。",
        "在打开的 Whop 页面完成付款。",
        "返回本机器人并点击“\U0001F4B3 我已付款”。",
    ],
}

_PAY_STEPS = {
    "en": [
        "Tap \U0001F3AF SELECT PACKAGE and choose a 7 / 14 / 30 day package.",
        "Complete the payment on the Whop checkout page.",
        "Return to the bot and tap \"\U0001F4B3 I HAVE PAID\".",
        "The administrator verifies your payment and sends a single-use activation token.",
        "Tap \"\U0001F511 ACTIVATE TOKEN\" and paste the token.",
    ],
    "id": [
        "Ketuk \U0001F3AF SELECT PACKAGE, lalu pilih paket 7 / 14 / 30 hari.",
        "Selesaikan pembayaran di halaman checkout Whop.",
        "Kembali ke bot dan ketuk \"\U0001F4B3 SAYA SUDAH MEMBAYAR\".",
        "Administrator memverifikasi pembayaran Anda, lalu mengirim token aktivasi sekali pakai.",
        "Ketuk \"\U0001F511 ACTIVATE TOKEN\" dan tempel token Anda.",
    ],
    "vi": [
        "Nhấn \U0001F3AF SELECT PACKAGE và chọn gói 7 / 14 / 30 ngày.",
        "Hoàn tất thanh toán trên trang checkout Whop.",
        "Quay lại bot và nhấn \"\U0001F4B3 TÔI ĐÃ THANH TOÁN\".",
        "Quản trị viên xác minh thanh toán và gửi token kích hoạt dùng một lần.",
        "Nhấn \"\U0001F511 ACTIVATE TOKEN\" và dán token của bạn.",
    ],
    "hi": [
        "\U0001F3AF SELECT PACKAGE दबाएँ और 7 / 14 / 30 दिन का पैकेज चुनें।",
        "Whop चेकआउट पेज पर भुगतान पूरा करें।",
        "बॉट पर वापस आएँ और \"\U0001F4B3 मैंने भुगतान कर दिया है\" दबाएँ।",
        "एडमिन आपका भुगतान सत्यापित करके एकल-उपयोग एक्टिवेशन टोकन भेजेगा।",
        "\"\U0001F511 ACTIVATE TOKEN\" दबाएँ और अपना टोकन पेस्ट करें।",
    ],
    "zh": [
        "点击 \U0001F3AF SELECT PACKAGE 并选择 7 / 14 / 30 天套餐。",
        "在 Whop 结账页面完成付款。",
        "返回机器人并点击“\U0001F4B3 我已付款”。",
        "管理员核验付款后，会向您发送一次性激活令牌。",
        "点击“\U0001F511 ACTIVATE TOKEN”并粘贴您的令牌。",
    ],
}


def _guide(lang: str, steps, tag: str) -> str:
    localized = steps.get(lang, steps["en"])
    body = "\n".join(f"{i}. {s}" for i, s in enumerate(localized, 1))
    return f"{line(tag, 'SIMPLE ROUTE >>>')}\n{body}"


def buy_guide(lang: str, tag: str = "PAYMENT") -> str:
    """Condensed 3-step purchase guide (plain language, localized)."""
    return _guide(lang, _BUY_STEPS, tag)


def pay_guide(lang: str, tag: str = "PAYMENT") -> str:
    """Full 5-step purchase + activation guide (plain language, localized)."""
    return _guide(lang, _PAY_STEPS, tag)
