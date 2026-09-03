"""Fail CI when forbidden legacy runtime contracts reappear."""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
CODE_PATHS = [ROOT / "app.py", ROOT / "api_handler.py", ROOT / "price_sources.py", ROOT / "market_candles.py", ROOT / "whop_api_phase2.py", ROOT / "whop_webhook_phase2.py"]

FORBIDDEN = {
    "TWELVEDATA_API_KEY": "TwelveData credentials are forbidden; GoldAPI is the market-data contract.",
    "api.twelvedata.com": "TwelveData runtime endpoint is forbidden.",
    "drop_pending_updates=True": "Telegram webhook registration must preserve pending updates.",
}


def main() -> int:
    violations: list[str] = []
    for path in CODE_PATHS:
        source = path.read_text(encoding="utf-8")
        for needle, reason in FORBIDDEN.items():
            if needle in source:
                violations.append(f"{path.relative_to(ROOT)}: {needle!r} — {reason}")
    if violations:
        print("PRODUCTION CONTRACT GUARD: FAIL")
        print("\n".join(violations))
        return 1
    print("PRODUCTION CONTRACT GUARD: PASS — legacy runtime contracts absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
