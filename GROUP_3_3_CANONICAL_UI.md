# Group 3.3 — Canonical UI Terms

Status: LOCKED

## Persistent navigation

Use exactly one canonical form on every customer-facing keyboard:

- `🏠 Menu` — callback `nav:home`
- `👨‍💼 Akun` — callback `screen:account`

Keep this pair as the final keyboard row.

## Status

Use exactly these status labels and emojis in the header:

- Active state: `Aktif 🟢`
- Inactive state: `Nonaktif 🔴`

Render the status label through i18n while keeping the emoji mapping fixed.

## Refresh

Use one canonical refresh action:

- `↻ Segarkan` in Indonesian
- `↻ Refresh` in English

The `↻` symbol is the single refresh indicator.

## Loading

Use one canonical loading action through i18n:

- Indonesian: `Memuat...`
- English: `Loading...`
- Spanish: `Cargando...`

Deliver it only through Telegram callback feedback (`query.answer(..., show_alert=False)`).

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
