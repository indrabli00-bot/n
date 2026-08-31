from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGETS = [ROOT / "main.py", ROOT / "premium_visuals.py", ROOT / "terminal_style.py"]
WHITELIST_PATH = ROOT / "UI_WHITELIST.txt"

# These are the actual presentation boundaries. `_present()` applies the
# per-user localization pass before Telegram receives the text; `panel()` is
# a formatter whose output is subsequently passed to `_present()`.
UI_SINK_NAMES = {
    "InlineKeyboardButton",
    "reply_text", "edit_message_text", "send_message",
    "set_my_description", "set_my_short_description",
}
ADMIN_ONLY_PREFIXES = ("addtoken_command", "listusers_command", "fulfillment_command", "reconcile_command", "user_command", "revoke_command")
PRESENTATION_BOUNDARIES = {"_present", "panel"}
MACHINE_PREFIXES = (
    "screen:", "nav:", "action:", "paid:", "settings:",
    "tg://", "http://", "https://",
)
DECORATIVE = set("━─┌┐┍┑└┘┕┙│◆◇◈◉○●★☆🎯🟢🟡🔵⚙️🌐💎🧠📈📊👑↻←⌂⚠✕✓🔑⌁")
TRANSLATION_CALLS = {"t", "_t", "_lang_text"}


def load_whitelist() -> set[str]:
    if not WHITELIST_PATH.exists():
        return set()
    return {
        line.strip()
        for line in WHITELIST_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def is_machine(value: str) -> bool:
    value = value.strip()
    if not value:
        return True
    if any(value.startswith(prefix) for prefix in MACHINE_PREFIXES):
        return True
    if all(ch in DECORATIVE or ch.isspace() for ch in value):
        return True
    return value.isdigit()


def call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def is_translation_call(node: ast.Call) -> bool:
    return call_name(node) in TRANSLATION_CALLS


def contains_translation_call(expr: ast.AST) -> bool:
    return any(isinstance(n, ast.Call) and is_translation_call(n) for n in ast.walk(expr))


def function_for_line(tree: ast.AST, line: int):
    candidates = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.lineno <= line <= getattr(node, "end_lineno", node.lineno)
    ]
    return max(candidates, key=lambda node: node.lineno, default=None)


def has_localization_call(function: ast.AST | None) -> bool:
    if function is None:
        return False
    return any(
        isinstance(node, ast.Call) and call_name(node) == "_localized_text"
        for node in ast.walk(function)
    )


def ui_expressions(tree: ast.AST) -> list[ast.AST]:
    expressions: list[ast.AST] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = call_name(node)
        if name not in UI_SINK_NAMES or is_translation_call(node):
            continue
        function = function_for_line(tree, node.lineno)
        if function is not None and function.name in ADMIN_ONLY_PREFIXES:
            continue

        if name == "InlineKeyboardButton":
            if node.args:
                expressions.append(node.args[0])
        else:
            expressions.extend(
                kw.value for kw in node.keywords
                if kw.arg in {"description", "short_description", "text", "caption"}
            )
            if node.args:
                expressions.append(node.args[0])
    return expressions


def validate_presentation_boundary(tree: ast.AST, path: pathlib.Path, violations: list[str]) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != "_present":
            continue
        if not has_localization_call(node):
            violations.append(
                f"{path.relative_to(ROOT)}:{node.lineno}: _present must apply _localized_text before rendering"
            )


def main() -> int:
    whitelist = load_whitelist()
    violations: list[str] = []

    for path in TARGETS:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        validate_presentation_boundary(tree, path, violations)

        for expr in ui_expressions(tree):
            if contains_translation_call(expr):
                continue
            for node in ast.walk(expr):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                    continue
                value = node.value.strip()
                if not value or value in whitelist or is_machine(value):
                    continue
                if any(ch.isalpha() for ch in value):
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: UI literal {value!r}")

    if violations:
        print("UI HARDCODE GUARD: FAIL")
        print("Violations found:")
        print("\n".join(dict.fromkeys(violations)))
        return 1

    print("UI HARDCODE GUARD: PASS — 0 violations found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
