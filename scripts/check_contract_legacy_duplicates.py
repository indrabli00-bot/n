"""Static contract audit for removed controllers, duplicate engines and stale source contracts."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_ABSENT = (
    "ui_contract.py",
    "instant_start.py",
    "callback_guard.py",
    "premium_visuals.py",
)
REQUIRED_PRESENT = (
    "main.py",
    "app.py",
    "api_handler.py",
    "smc_engine.py",
    "market_candles.py",
    "price_sources.py",
    "whop_webhook_phase2.py",
    "whop_storage.py",
    "runtime_hardening.py",
)
LEGACY_PRICE_SOURCES = (
    "gold-api.com",
    "goldprice.org",
    "TwelveData",
    "TWELVEDATA_API_KEY",
)


def main() -> int:
    errors: list[str] = []
    for name in REQUIRED_ABSENT:
        if (ROOT / name).exists():
            errors.append(f"legacy controller/module still present: {name}")
    for name in REQUIRED_PRESENT:
        if not (ROOT / name).exists():
            errors.append(f"required canonical module missing: {name}")

    api = (ROOT / "api_handler.py").read_text(encoding="utf-8")
    if "def _simulate_technical_indicators" in api:
        errors.append("deprecated _simulate_technical_indicators compatibility alias remains; use get_technical_indicators")
    for literal in LEGACY_PRICE_SOURCES:
        if literal in api or literal in (ROOT / "price_sources.py").read_text(encoding="utf-8"):
            # TwelveData is explicitly forbidden; alternate price sources are
            # also forbidden by the current contract. Keep this guard strict.
            errors.append(f"legacy/secondary market source remains: {literal}")

    main_src = (ROOT / "main.py").read_text(encoding="utf-8")
    if "import smc_engine" in main_src or "from smc_engine" in main_src:
        errors.append("main.py imports smc_engine directly; signal-engine ownership must remain in api_handler.py")
    if "def render_signal" not in main_src:
        errors.append("canonical main.py signal renderer missing")
    if "api_handler.get_latest_smc_signal()" not in main_src:
        errors.append("main.py signal renderer is not using api_handler.get_latest_smc_signal()")
    if "api_handler.get_technical_indicators(" not in main_src:
        errors.append("main.py analysis renderer is not using api_handler.get_technical_indicators()")
    if "_simulate_technical_indicators" in main_src:
        errors.append("main.py still references deprecated simulation API")

    print("CONTRACT/DEDUP GUARD: FAIL") if errors else print("CONTRACT/DEDUP GUARD: PASS")
    for error in errors:
        print(f"- {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
