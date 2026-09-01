# NEURAL GOLD — Premium Telegram UI

## Group 3.3 canonical render contract

The customer-facing UI follows a single rendering order:

1. Header — UTC timestamp, operator, and status.
2. Terminal — responsive preformatted content with a configured maximum width.
3. Action text — optional plain-text guidance.
4. Inline keyboard — contextual actions followed by persistent `[ 🏠 Menu ] [ 👨‍💼 Akun ]` navigation.

The `main.py` caller owns the Telegram `<pre>` tag. `terminal_style.render_terminal_box()` returns terminal content only and uses the canonical `max_width=40` default.

## Home

- `NEURAL GOLD v3.2 // OPERATOR CONSOLE` appears in the terminal content.
- Operator and status appear once in the header.
- Active users receive the canonical module buttons: `MARKET PULSE`, `NEURAL STRIKES`, and `STRUCTURE MAP`.
- Inactive users receive the package checkout buttons and activation/payment actions.
- Persistent navigation remains the final keyboard row.

## Navigation

Every customer screen ends with the persistent navigation row:
- `[ 🏠 Menu ]`
- `[ 👨‍💼 Akun ]`

Contextual screens use their own action buttons above this row. The legacy Back navigation is no longer part of the customer keyboard contract.

## Price

Tap `MARKET PULSE` → live XAU/USD data is fetched and presented inside the canonical terminal area.

## Signal

Tap `NEURAL STRIKES` → the existing neural signal engine is presented inside the canonical terminal area.

## Analysis

Tap `STRUCTURE MAP` → the existing technical/market engine is presented inside the canonical terminal area.

## Account

Tap `Akun` → real-time subscription status and account information are presented using the canonical header and terminal structure.

## Access

Access and checkout flows remain intact. Existing package checkout and token activation/payment handlers remain unchanged by the Group 3.3 visual refactor.

## Render ownership

`premium_visuals.py` remains a compatibility module and does not override `main.py` render functions. `terminal_style.py` owns reusable terminal/header/navigation helpers; `main.py` owns message composition and `<pre>` placement.

## Verification

Group 3.3 finalization was validated in GitHub Actions before commit with:
- Python compile: PASS
- Pytest: 54 PASS
- Full unittest regression: 48 PASS
- Static UI hardcode guard: PASS — 0 violations
