"""Direct biconditional elimination must use the premise-aware theorem helper."""

from __future__ import annotations

import ast
from pathlib import Path


SEED_DIRECTORY = Path(__file__).parents[1] / "dem" / "db" / "seeds"


def test_no_legacy_iff_implication_is_consumed_only_by_mp() -> None:
    """Reject direct and single-use ``iff_left/right`` MP expansions."""
    legacy_calls: list[str] = []

    for path in SEED_DIRECTORY.glob("*.py"):
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=str(path))
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"iff_left", "iff_right"}
            ):
                continue
            parent = parents.get(node)
            if (
                isinstance(parent, ast.Call)
                and isinstance(parent.func, ast.Attribute)
                and parent.func.attr == "mp"
                and len(parent.args) >= 2
                and parent.args[1] is node
            ):
                legacy_calls.append(f"{path.name}:{node.lineno}")
                continue

            if not (
                isinstance(parent, ast.Assign)
                and len(parent.targets) == 1
                and isinstance(parent.targets[0], ast.Name)
            ):
                continue
            scope = parent
            while scope is not None and not isinstance(scope, ast.FunctionDef):
                scope = parents.get(scope)
            if scope is None:
                continue
            name = parent.targets[0].id
            loads = [
                candidate
                for candidate in ast.walk(scope)
                if isinstance(candidate, ast.Name)
                and isinstance(candidate.ctx, ast.Load)
                and candidate.id == name
            ]
            if len(loads) != 1:
                continue
            consumer = parents.get(loads[0])
            if (
                isinstance(consumer, ast.Call)
                and isinstance(consumer.func, ast.Attribute)
                and consumer.func.attr == "mp"
                and len(consumer.args) >= 2
                and consumer.args[1] is loads[0]
            ):
                legacy_calls.append(f"{path.name}:{node.lineno}")

    assert legacy_calls == []
