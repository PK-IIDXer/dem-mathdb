"""Replaceable interpretation interface and the Phase 2 null implementation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

from demai.tasks import InterpreterInput, InterpreterOutput, TaskName


@dataclass(frozen=True)
class UnavailableResult:
    """A normal result used when no interpreter provider is configured."""

    task: TaskName
    reason: Literal["not_configured"] = "not_configured"
    available: Literal[False] = field(default=False, init=False)


@runtime_checkable
class Interpreter(Protocol):
    def interpret(
        self, request: InterpreterInput
    ) -> InterpreterOutput | UnavailableResult:
        """Interpret one authoring request without committing it to DEM."""


class NullInterpreter:
    """Deterministic interpreter used until an explicit provider is introduced."""

    def interpret(self, request: InterpreterInput) -> UnavailableResult:
        return UnavailableResult(task=request.task)
