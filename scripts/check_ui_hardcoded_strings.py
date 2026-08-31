from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGETS = [ROOT / "main.py", ROOT / "premium_visuals.py", ROOT / "terminal_style.py"]
WHITELIST_PATH = ROOT / "UI_WHITELIST.txt"

UI_SINK_NAMES = {
    "InlineKeyboardButton", "panel", "_present", "_answer_loading",
    "reply_text", "edit_message_text", "send_message",
    "set_my_description", "set_my_short_description",
}
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


def parentize(tree: ast.AST) -> None:
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            setattr(child, "parent", parent)


def contains_translation_call(expr: ast.AST) -> bool:
    return any(isinstance(n, ast.Call) and is_translation_call(n) for n in ast.walk(expr))


def nearest_assignment(function: ast.FunctionDef | ast.AsyncFunctionDef, name: str, use_line: int) -> ast.AST | None:
    candidates: list[ast.AST] = []
    for node in ast.walk(function):
        if isinstance(node, ast.Assign) and node.lineno < use_line:
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                candidates.append(node.value)
        elif isinstance(node, ast.AnnAssign) and node.lineno < use_line:
            if isinstance(node.target, ast.Name) and node.target.id == name:
                candidates.append(node.value)
    return candidates[-1] if candidates else None


def function_for_line(tree: ast.AST, line: int):
    candidates = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.lineno <= line <= getattr(node, "end_lineno", node.lineno)
    ]
    return max(candidates, key=lambda node: node.lineno, default=None)


def ui_expressions(tree: ast.AST) -> list[ast.AST]:
    expressions: list[ast.AST] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = call_name(node)
        if name not in UI_SINK_NAMES or is_translation_call(node):
            continue

        if name == "InlineKeyboardButton":
            if node.args:
                expressions.append(node.args[0])
        elif name == "panel":
            expressions.extend(node.args)
        elif name == "_answer_loading":
            if node.args:
                expressions.append(node.args[-1])
        elif name in {"_present", "reply_text", "edit_message_text", "send_message"}:
            if name == "_present" and len(node.args) >= 2:
                text_expr = node.args[1]
            elif node.args:
                text_expr = node.args[0]
            else:
                text_expr = next((kw.value for kw in node.keywords if kw.arg in {"text", "caption"}), None)
            if text_expr is not None:
                expressions.append(text_expr)
                if isinstance(text_expr, ast.Name):
                    function = function_for_line(tree, node.lineno)
                    if function:
                        resolved = nearest_assignment(function, text_expr.id, node.lineno)
                        if resolved is not None:
                            expressions.append(resolved)
        else:
            expressions.extend(
                kw.value for kw in node.keywords
                if kw.arg in {"description", "short_description", "text", "caption"}
            )
    return expressions


def main() -> int:
    whitelist = load_whitelist()
    violations: list[str] = []

    for path in TARGETS:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        parentize(tree)

        # Explicitly flag the old post-process translation table as UI source.
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "_PHRASE_MAP"
                for target in node.targets
            ):
                for child in ast.walk(node.value):
                    if isinstance(child, ast.Constant) and isinstance(child.value, str) and child.value.strip():
                        value = child.value.strip()
                        if value not in whitelist and not is_machine(value):
                            violations.append(
                                f"{path.relative_to(ROOT)}:{child.lineno}: _PHRASE_MAP UI literal {value!r}"
                            )

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
