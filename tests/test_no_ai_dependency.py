"""The core application remains importable with the optional AI layer blocked."""

from __future__ import annotations

import importlib.abc
import inspect
from pathlib import Path
import subprocess
import sys
import textwrap

import demai.interpreter
from demai import (
    ErrorExplainInput,
    FormulaInput,
    Interpreter,
    LemmaSelectInput,
    NullInterpreter,
    TheoremInput,
    UnavailableResult,
)
from dem.types import Token


def test_core_packages_import_when_demai_is_blocked() -> None:
    repository = Path(__file__).resolve().parents[1]
    script = textwrap.dedent(
        """
        import importlib
        import importlib.abc
        import pkgutil
        import sys

        class RejectDemai(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "demai" or fullname.startswith("demai."):
                    raise ImportError(f"forbidden dependency: {fullname}")
                return None

        sys.meta_path.insert(0, RejectDemai())
        for root_name in ("dem", "demlang", "webapi"):
            root = importlib.import_module(root_name)
            for module in pkgutil.walk_packages(root.__path__, root_name + "."):
                importlib.import_module(module.name)
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repository,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr


def test_null_interpreter_is_the_only_concrete_interpreter() -> None:
    concrete = [
        value
        for _, value in inspect.getmembers(demai.interpreter, inspect.isclass)
        if value.__module__ == demai.interpreter.__name__
        and value is not UnavailableResult
        and not getattr(value, "_is_protocol", False)
    ]
    assert concrete == [NullInterpreter]
    assert isinstance(NullInterpreter(), Interpreter)


def test_null_interpreter_returns_unavailable_for_every_task() -> None:
    token = Token(symbol_id=1)
    requests = (
        FormulaInput("a formula"),
        TheoremInput("a theorem"),
        LemmaSelectInput((token,), ((token,),)),
        ErrorExplainInput("proof.invalid", "invalid proof"),
    )
    interpreter = NullInterpreter()
    assert [interpreter.interpret(request) for request in requests] == [
        UnavailableResult(task=request.task) for request in requests
    ]
