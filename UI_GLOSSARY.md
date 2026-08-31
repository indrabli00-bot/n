# NEURAL GOLD UI Glossary & Hardcode Policy

## Purpose

Keep customer-facing language consistent across all Telegram screens while allowing deliberate product terminology and machine-readable values to remain literal.

## Allowed hardcoded human-facing terms

### Brand / product names
- NEURAL GOLD
- NEURAL GOLD v3.2

### Trading / market terms
- XAU/USD
- XAUUSD
- BUY
- SELL
- HOLD
- ENTRY
- STOP LOSS
- TP1
- TP2
- TP3
- BID
- ASK
- RSI
- MACD
- EMA
- ATR
- STOCH
- BOLLINGER
- UTC

### Technical labels that are intentionally product-styled
- SYSTEM
- STATUS
- ACCESS
- ANALYSIS
- CORE
- SECURITY
- ERROR
- FAULT
- PAYMENT
- CLEARANCE
- KEYGEN
- OPERATOR
- CONSOLE
- INITIALIZATION
- INTELLIGENCE REPORT

These terms are retained as a deliberate terminal/product vocabulary. Customer-facing explanatory sentences and action labels remain localized through `i18n.py`.

### Non-UI / machine-readable strings
- callback data such as `screen:price`, `nav:home`, `action:token`
- Python identifiers, function names, class names, database fields, environment variable names
- URLs and URL schemes
- code/configuration values
- version identifiers and timestamps
- box-drawing characters and decorative symbols such as `━`, `┌`, `┐`, `└`, `┘`, `◆`

## Localization rule

Human-language action copy, sentences, button labels, package descriptions, help text, status explanations, and payment instructions belong in `i18n.py` and are retrieved with the active language.

The presentation boundary accepts already-localized text. Rendering modules call the localization catalog before passing text into the presentation boundary.

When a literal is not listed here and is intended for the user, add a translation key instead of embedding the sentence directly in a rendering module.
