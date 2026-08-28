"""NEURAL GOLD v3.2 — premium visual presentation layer.

Business logic remains in main.py. This layer adds a generated Telegram-ready
visual card before each premium screen, using the official Neural Gold SVG as
the identity anchor.
"""
from __future__ import annotations

from telegram import InlineKeyboardMarkup, Update
from visuals import visual_path


def _visual_key(text: str) -> str:
    upper = text.upper()
    if "ALPHA-SENTI MATRIX" in upper or "MARKET ANALYSIS" in upper:
        return "matrix"
    if "NEURAL SIGNAL" in upper or "NEURAL-SIGNAL" in upper:
        return "signal"
    if "ACCOUNT INTELLIGENCE" in upper or "<B>♛ ACCOUNT" in upper or "ACCOUNT STATUS" in upper:
        return "account"
    if "ACTIVATE TOKEN" in upper or "SECURE ACTIVATION" in upper:
        return "token"
    if "PAYMENT CONFIRMED" in upper or "ACCESS ACTIVATED" in upper:
        return "success"
    if "CHECKOUT" in upper:
        return "checkout"
    if "PREMIUM ACCESS" in upper or "ACCESS PACKAGES" in upper or "ACCESS / PLANS" in upper:
        return "access"
    return "home"


def _short_caption(text: str) -> str:
    key = _visual_key(text)
    titles = {
        "home": "NEURAL GOLD // v3.2",
        "matrix": "ALPHA-SENTI MATRIX // XAU/USD",
        "signal": "NEURAL-SIGNAL // XAU/USD",
        "account": "ACCOUNT STATUS // PREMIUM ACCESS",
        "token": "ACTIVATE TOKEN // SECURE ACCESS",
        "access": "NEURAL GOLD // PREMIUM ACCESS",
        "checkout": "CHECKOUT // SECURE PAYMENT ROUTE",
        "success": "PAYMENT CONFIRMED // ACCESS FULFILLMENT",
    }
    return f"<b>{titles[key]}</b>\n<i>NEURAL GOLD v3.2</i>"


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
        asset = visual_path(_visual_key(localized))

        if not asset:
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
                with open(asset, "rb") as fh:
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
                with open(asset, "rb") as fh:
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
