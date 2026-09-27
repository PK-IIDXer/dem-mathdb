"""DB-independent request and response types for interpretation tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping, TypeAlias

from dem.types import Token


TaskName: TypeAlias = Literal["formula", "theorem", "lemma_select", "error_explain"]


@dataclass(frozen=True)
class FormulaInput:
    description: str
    task: Literal["formula"] = field(default="formula", init=False)


@dataclass(frozen=True)
class FormulaOutput:
    tokens: tuple[Token, ...]
    task: Literal["formula"] = field(default="formula", init=False)


@dataclass(frozen=True)
class TheoremInput:
    description: str
    task: Literal["theorem"] = field(default="theorem", init=False)


@dataclass(frozen=True)
class TheoremOutput:
    premises: tuple[tuple[Token, ...], ...]
    conclusion: tuple[Token, ...]
    task: Literal["theorem"] = field(default="theorem", init=False)


@dataclass(frozen=True)
class LemmaSelectInput:
    goal_tokens: tuple[Token, ...]
    argument_tokens: tuple[tuple[Token, ...], ...] = ()
    limit: int = 20
    task: Literal["lemma_select"] = field(default="lemma_select", init=False)

    def __post_init__(self) -> None:
        if self.limit <= 0:
            raise ValueError("limit must be > 0")


@dataclass(frozen=True)
class LemmaSelectOutput:
    theorem_ids: tuple[int, ...]
    task: Literal["lemma_select"] = field(default="lemma_select", init=False)


@dataclass(frozen=True)
class ErrorExplainInput:
    error_code: str
    message: str
    context: Mapping[str, object] = field(default_factory=dict)
    task: Literal["error_explain"] = field(default="error_explain", init=False)


@dataclass(frozen=True)
class ErrorExplainOutput:
    explanation: str
    task: Literal["error_explain"] = field(default="error_explain", init=False)


InterpreterInput: TypeAlias = (
    FormulaInput | TheoremInput | LemmaSelectInput | ErrorExplainInput
)
InterpreterOutput: TypeAlias = (
    FormulaOutput | TheoremOutput | LemmaSelectOutput | ErrorExplainOutput
)
