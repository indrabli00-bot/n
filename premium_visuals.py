"""NEURAL GOLD v3.2 — premium visual presentation layer.

This module keeps business logic in main.py untouched while adding a consistent
visual header to Telegram screens. It is intentionally isolated so visual
changes cannot alter checkout, webhook, token, or database logic.
"""
from __future__ import annotations

from pathlib import Path

from telegram import InlineKeyboardMarkup, Update

ASSET_DIR = Path(__file__).resolve().parent / "assets"

ASSETS = {
    "logo": ASSET_DIR / "logo_neural_gold.png",
    "matrix": ASSET_DIR / "bg_matrix.jpg",
    "signal": ASSET_DIR / "bg_signal.jpg",
    "account": ASSET_DIR / "bg_account.jpg",
    "token": ASSET_DIR / "bg_token.jpg",
    "plans": ASSET_DIR / "bg_plans.jpg",
}


def _asset_for_text(text: str) -> Path:
    upper = text.upper()
    if "ALPHA-SENTI MATRIX" in upper or "MARKET ANALYSIS" in upper:
        return ASSETS["matrix"]
    if "NEURAL SIGNAL" in upper or "NEURAL-SIGNAL" in upper:
        return ASSETS["signal"]
    if "ACCOUNT INTELLIGENCE" in upper or "<B>♛ ACCOUNT" in upper or "ACCOUNT STATUS" in upper:
        return ASSETS["account"]
    if "ACTIVATE TOKEN" in upper or "SECURE ACTIVATION" in upper:
        return ASSETS["token"]
    if "PREMIUM ACCESS" in upper or "ACCESS PACKAGES" in upper or "ACCESS / PLANS" in upper:
        return ASSETS["plans"]
    return ASSETS["logo"]


def _short_caption(text: str) -> str:
    """Keep the visual header concise; the full intelligence brief follows it."""
    upper = text.upper()
    title = "NEURAL GOLD // v3.2"
    if "ALPHA-SENTI MATRIX" in upper or "MARKET ANALYSIS" in upper:
        title = "ALPHA-SENTI MATRIX // XAU/USD"
    elif "NEURAL SIGNAL" in upper or "NEURAL-SIGNAL" in upper:
        title = "NEURAL-SIGNAL // XAU/USD"
    elif "ACCOUNT" in upper:
        title = "ACCOUNT STATUS // PREMIUM ACCESS"
    elif "ACTIVATE" in upper:
        title = "ACTIVATE TOKEN // SECURE ACCESS"
    elif "PREMIUM ACCESS" in upper or "ACCESS PACKAGES" in upper:
        title = "NEURAL GOLD // PREMIUM ACCESS"
    return f"<b>{title}</b>\n<i>NEURAL GOLD v3.2</i>"


def install() -> None:
    """Install the visual presenter into main._present at application startup."""
    import main

    if getattr(main, "_premium_visual_installed", False):
        return

    original_present = main._present

    async def visual_present(
        update: Update,
        text: str,
        keyboard: InlineKeyboardMarkup,
        edit: bool = True,
    ) -> None:
        query = update.callback_query
        localized = main._localized_text(update, text)
        asset = _asset_for_text(localized)

        if not asset.exists():
            await original_present(update, text, keyboard, edit=edit)
            return

        if query and query.message:
            try:
                await query.answer()
            except Exception:
                pass
            try:
                await query.message.delete()
            except Exception:
                pass
            try:
                with asset.open("rb") as fh:
                    await query.message.chat.send_photo(
                        photo=fh,
                        caption=_short_caption(localized),
                        parse_mode="HTML",
                    )
                await query.message.chat.send_message(
                    text=localized,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
                return
            except Exception:
                await original_present(update, text, keyboard, edit=False)
                return

        if update.message:
            try:
                with asset.open("rb") as fh:
                    await update.message.reply_photo(
                        photo=fh,
                        caption=_short_caption(localized),
                        parse_mode="HTML",
                    )
                await update.message.reply_text(
                    localized,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
                return
            except Exception:
                await original_present(update, text, keyboard, edit=False)
                return

        await original_present(update, text, keyboard, edit=edit)

    main._present = visual_present
    main._premium_visual_installed = True
