# Group 3.3 — Canonical UI Terms

Status: LOCKED

## Persistent navigation

Use exactly one canonical form on every customer-facing keyboard:

- `🏠 ⌂ MENU` — callback `nav:home`
- `👨‍💼 ACCOUNT` — callback `screen:account`

Keep this pair as the final keyboard row.

## Status

Render active/inactive status through `i18n.py` while keeping the product's fixed status semantics and emoji mapping.

## Refresh

Use one canonical refresh action through i18n. The `↻` symbol is the single refresh indicator.

## Loading

Use one canonical loading action through i18n and deliver it only through Telegram callback feedback (`query.answer(..., show_alert=False)`).

## Brand/module terms

Keep these terms in English in every language:

- `NEURAL GOLD`
- `NEURAL GOLD v3.2`
- `MARKET PULSE`
- `NEURAL STRIKES`
- `STRUCTURE MAP`
- `OPERATOR HUB`
- `SYSTEM SYNC`
- `XAU/USD`
- `GOLD SPOT`

## Back navigation

Customer-facing keyboards use zero Back navigation. The persistent navigation row above is the canonical replacement.
