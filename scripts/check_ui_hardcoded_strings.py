from __future__ import annotations

import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGETS = [ROOT / "main.py", ROOT / "premium_visuals.py", ROOT / "terminal_style.py"]
WHITELIST = {
    "NEURAL GOLD", "NEURAL GOLD v3.2", "XAU/USD", "XAUUSD", "BUY", "SELL", "HOLD",
    "ENTRY", "STOP LOSS", "TP1", "TP2", "TP3", "BID", "ASK", "RSI", "MACD", "EMA",
    "ATR", "STOCH", "BOLLINGER", "UTC", "SYSTEM", "STATUS", "ACCESS", "ANALYSIS", "CORE",
    "SECURITY", "ERROR", "FAULT", "PAYMENT", "CLEARANCE", "KEYGEN", "OPERATOR", "CONSOLE",
    "INITIALIZATION", "INTELLIGENCE REPORT", "LIVE", "PREMIUM", "NEURAL SIGNAL",
}
MACHINE_PREFIXES = ("screen:", "nav:", "action:", "paid:", "settings:", "tg://", "http://", "https://")
NON_HUMAN_PATTERNS = [re.compile(r"^[A-Z_][A-Z0-9_./:-]*$"), re.compile(r"^\d+(\.\d+)?$"), re.compile(r"^[━─┌┐└┘│◆◇◈◉○●★☆🎯🟢🟡🔵⚙️🌐💎🧠📈📊👑↻←⌂⚠✕✓🔑⌁]+$")]


def is_machine(value: str) -> bool:
    if any(value.startswith(p) for p in MACHINE_PREFIXES):
        return True
    if "\\n" in value and all(any(ch.isalpha() for ch in part) is False for part in value.split("\\n")):
        return True
    return any(p.fullmatch(value.strip()) for p in NON_HUMAN_PATTERNS)


def is_localization_call(node: ast.AST) -> bool:
    parent = getattr(node, "parent", None)
    while parent is not None:
        if isinstance(parent, ast.Call) and isinstance(parent.func, ast.Name) and parent.func.id in {"t", "_t", "_lang_text", "_localized_text"}:
            return True
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            break
        parent = getattr(parent, "parent", None)
    return False


def main() -> int:
    violations: list[str] = []
    for path in TARGETS:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        parents = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                setattr(child, "parent", parent)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str) or not node.value.strip():
                continue
            value = node.value.strip()
            if value in WHITELIST or is_machine(value) or is_localization_call(node):
                continue
            if any(ch.isalpha() for ch in value):
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: {value!r}")
    if violations:
        print("UI HARDCODE GUARD: FAIL")
        print("Violations found:")
        print("\n".join(violations))
        return 1
    print("UI HARDCODE GUARD: PASS — 0 violations found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
