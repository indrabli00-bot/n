# NEURAL GOLD — Premium Telegram UI

## Canonical render contract

The customer-facing UI follows a single rendering order:

1. Header — UTC timestamp, operator, and status.
2. Terminal — responsive preformatted content with a configured maximum width.
3. Action text — optional plain-text guidance.
4. Inline keyboard — contextual actions followed by persistent `[ 🏠 ⌂ MENU ] [ 👨‍💼 ACCOUNT ]` navigation.

`main.py` is the single canonical Telegram UI/controller. `terminal_style.py` owns reusable terminal/header/navigation helpers. `main.py` owns message composition and `<pre>` placement.

## Home

- `NEURAL GOLD v3.2 // OPERATOR CONSOLE` appears in the terminal content.
- Operator and status appear once in the header.
- Active users receive `MARKET PULSE`, `NEURAL STRIKES`, and `STRUCTURE MAP`.
- Inactive users receive package checkout and activation/payment actions.
- Persistent navigation remains the final keyboard row.

## Navigation

Every customer screen ends with:
- `[ 🏠 ⌂ MENU ]`
- `[ 👨‍💼 ACCOUNT ]`

Contextual screens use their own action buttons above this row. Legacy Back navigation is not part of the customer keyboard contract.

## Modules

- `MARKET PULSE` → live XAU/USD data.
- `NEURAL STRIKES` → neural signal engine.
- `STRUCTURE MAP` → technical/market analysis engine.
- `ACCOUNT` → real-time subscription and account information.

## Access

Access, checkout, and token activation flows remain part of the canonical `main.py` controller.

## Verification

The current CI workflow is the source of truth for verification results. Documentation must not hardcode historical test counts.
