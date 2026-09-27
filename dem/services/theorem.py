from __future__ import annotations

from dataclasses import dataclass
from math import log1p
from typing import Mapping, Sequence

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from dem.db.seed_labels import theorem_lookup_names
from dem.db.models.language import Formula, FormulaToken, Namespace, Symbol, SymbolType
from dem.db.models.tag import TheoremTag
from dem.db.models.theorem import Proof, ProofStep, Theorem, TheoremPremise
from dem.errors import ConflictError, NotFoundError, ValidationError
from dem.services.authoring_provenance import AuthoringVia, record_authoring_provenance
from dem.types import FormulaTypeName
from dem.types import SymbolMeta, SymbolTypeName, Token
from demlang.match import MatchResult, match_formulas
from dem.services.formula import FormulaService
from dem.identity import DEFAULT_NAMESPACE_NAME, ensure_namespace, new_entity_public_id


@dataclass(frozen=True)
class LemmaCandidate:
    """Database-independent input to the lemma ranker."""

    theorem_id: int
    conclusion_tokens: tuple[Token, ...]
    premise_tokens: tuple[tuple[Token, ...], ...]
    usage_count: int
    is_schematic: bool
    namespace_id: int


@dataclass(frozen=True)
class RankedLemma:
    theorem_id: int
    is_schematic: bool
    score: float


def match_theorem_constraints(
    premise_patterns: Sequence[Sequence[Token]],
    conclusion_pattern: Sequence[Token],
    arg_tokens: Sequence[Sequence[Token]],
    goal_tokens: Sequence[Token] | None,
    symbol_meta: Mapping[int, SymbolMeta],
    result: MatchResult | None = None,
) -> MatchResult | None:
    """Match one theorem against the premises and/or goal selected by a user."""
    if len(arg_tokens) > len(premise_patterns):
        return None
    constraints = [
        (premise, argument)
        for premise, argument in zip(premise_patterns, arg_tokens)
    ]
    if goal_tokens is not None:
        constraints.append((conclusion_pattern, goal_tokens))
    return match_formulas(constraints, symbol_meta, result)


def rank_lemma_candidates(
    candidates: Sequence[LemmaCandidate],
    *,
    goal_tokens: Sequence[Token] | None,
    arg_tokens: Sequence[Sequence[Token]] = (),
    symbol_meta: Mapping[int, SymbolMeta],
    recent_theorem_ids: frozenset[int] = frozenset(),
    current_namespace_id: int | None = None,
    shared_namespace_ids: frozenset[int] = frozenset(),
) -> list[RankedLemma]:
    """Return deterministic lemma ranks without consulting a database.

    A lemma of the namespace being worked in scores higher, and so does one of
    a namespace shared by every foundation (the logical layer): its theorems
    are the ones any proof may cite, and demoting them below the current
    foundation's own lemmas measurably costs hits."""
    if goal_tokens is None and not arg_tokens:
        raise ValueError("a goal or at least one argument is required")

    ranked: list[RankedLemma] = []
    for candidate in candidates:
        if match_theorem_constraints(
            candidate.premise_tokens,
            candidate.conclusion_tokens,
            arg_tokens,
            goal_tokens,
            symbol_meta,
        ) is None:
            continue
        score = (
            3.0 * log1p(candidate.usage_count)
            - (2.0 if candidate.is_schematic else 0.0)
            + (2.0 if candidate.theorem_id in recent_theorem_ids else 0.0)
            + (
                1.0
                if (
                    current_namespace_id is not None
                    and candidate.namespace_id == current_namespace_id
                )
                or candidate.namespace_id in shared_namespace_ids
                else 0.0
            )
        )
        ranked.append(
            RankedLemma(
                theorem_id=candidate.theorem_id,
                is_schematic=candidate.is_schematic,
                score=score,
            )
        )
    ranked.sort(key=lambda item: (-item.score, item.theorem_id))
    return ranked


class TheoremService:
    def __init__(
        self,
        session: Session,
        *,
        authoring_via: AuthoringVia | None = None,
    ) -> None:
        self._session = session
        self._authoring_via = authoring_via

    def register(
        self,
        name: str,
        conclusion_formula_id: int,
        premise_formula_ids: list[int] | None = None,
        description: str | None = None,
        remarks: str | None = None,
        namespace: str = DEFAULT_NAMESPACE_NAME,
        namespace_id: int | None = None,
        public_id_key: str | None = None,
    ) -> Theorem:
        """Register a conjecture.

        ``public_id_key`` is the seed / package-import path for keeping a
        theorem's birth identity (``dem.identity.public_id_from_key``); the
        REST API never passes it.
        """
        namespace_row = (
            self._session.get(Namespace, namespace_id)
            if namespace_id is not None
            else ensure_namespace(self._session, namespace)
        )
        if namespace_row is None:
            raise NotFoundError("Namespace", namespace_id or namespace)
        public_id = new_entity_public_id("theorem", namespace_row.name, name, public_id_key)
        premise_formula_ids = premise_formula_ids or []
        formulas = self._load_formulas([conclusion_formula_id, *premise_formula_ids])

        conclusion = formulas.get(conclusion_formula_id)
        if conclusion is None:
            raise NotFoundError("Formula", conclusion_formula_id)
        if conclusion.formula_type.name != FormulaTypeName.PROPOSITION.value:
            raise ValidationError("conclusion must be a proposition")

        for index, formula_id in enumerate(premise_formula_ids):
            premise = formulas.get(formula_id)
            if premise is None:
                raise NotFoundError("Formula", formula_id)
            if premise.formula_type.name != FormulaTypeName.PROPOSITION.value:
                raise ValidationError(f"premise at index {index} must be a proposition")

        existing = self._session.scalar(
            select(Theorem).where(
                Theorem.namespace_id == namespace_row.id, Theorem.name == name
            )
        )
        if existing is not None:
            raise ConflictError("Theorem", "name", name)
        if public_id_key is not None and self._session.scalar(
            select(Theorem.id).where(Theorem.public_id == public_id)
        ) is not None:
            raise ConflictError("Theorem", "public_id", public_id)

        theorem = Theorem(
            public_id=public_id,
            namespace_id=namespace_row.id,
            name=name,
            conclusion_formula_id=conclusion.id,
            status="conjecture",
            description=description.strip() if description and description.strip() else None,
            remarks=remarks,
        )
        self._session.add(theorem)
        self._session.flush()
        record_authoring_provenance(
            self._session,
            entity_kind="theorem",
            entity_id=theorem.id,
            via=self._authoring_via,
        )

        self._session.add_all(
            TheoremPremise(theorem_id=theorem.id, ord=ord_, formula_id=formula_id)
            for ord_, formula_id in enumerate(premise_formula_ids)
        )
        self._session.flush()
        return theorem

    def get(self, id: int) -> Theorem:
        row = self._session.get(Theorem, id)
        if row is None:
            raise NotFoundError("Theorem", id)
        return row

    def get_by_public_id(self, public_id: str) -> Theorem:
        row = self._session.scalar(select(Theorem).where(Theorem.public_id == public_id))
        if row is None:
            raise NotFoundError("Theorem", public_id)
        return row

    def get_by_name(self, name: str, namespace: str | None = None) -> Theorem:
        stmt = select(Theorem).where(Theorem.name.in_(theorem_lookup_names(name)))
        if namespace is not None:
            stmt = stmt.join(Namespace).where(Namespace.name == namespace)
        rows = list(self._session.scalars(stmt.limit(2)))
        if not rows:
            raise NotFoundError("Theorem", name)
        if len(rows) > 1:
            raise ValidationError(
                f"theorem name {name!r} is ambiguous",
                code="theorem.ambiguous_name",
                details={"name": name},
            )
        return rows[0]

    def list_all(
        self,
        search: str | None = None,
        tag_ids: list[int] | None = None,
        status: str | None = None,
    ) -> list[Theorem]:
        stmt = select(Theorem).order_by(Theorem.id)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(Theorem.name.ilike(like), Theorem.description.ilike(like)))
        if tag_ids:
            stmt = (
                stmt.join(TheoremTag, TheoremTag.theorem_id == Theorem.id)
                .where(TheoremTag.tag_id.in_(tag_ids))
                .distinct()
            )
        if status:
            stmt = stmt.where(Theorem.status == status)
        return list(self._session.scalars(stmt))

    def set_description(self, id: int, description: str | None) -> Theorem:
        theorem = self.get(id)
        theorem.description = description.strip() if description and description.strip() else None
        self._session.flush()
        return theorem

    def list_premises(self, theorem_id: int) -> list[tuple[int, Formula]]:
        self.get(theorem_id)
        rows = self._session.execute(
            select(TheoremPremise.ord, Formula)
            .join(Formula, TheoremPremise.formula_id == Formula.id)
            .where(TheoremPremise.theorem_id == theorem_id)
            .order_by(TheoremPremise.ord)
        ).all()
        return [(ord_, formula) for ord_, formula in rows]

    def list_used_in_theorems(self, id: int) -> list[Theorem]:
        """Theorems with a proof that cites one of this theorem's proofs
        directly as a lemma (a 'theorem' step whose applied_proof_id belongs
        to this theorem). Not transitive: a theorem that only cites this one
        through an intermediate lemma will not appear here."""
        self.get(id)
        cited_proof_ids = select(Proof.id).where(Proof.theorem_id == id)
        theorem_ids = list(
            self._session.scalars(
                select(Proof.theorem_id)
                .join(ProofStep, ProofStep.proof_id == Proof.id)
                .where(ProofStep.step_kind == "theorem", ProofStep.applied_proof_id.in_(cited_proof_ids))
                .distinct()
            )
        )
        if not theorem_ids:
            return []
        return list(
            self._session.scalars(select(Theorem).where(Theorem.id.in_(theorem_ids)).order_by(Theorem.id))
        )

    def list_applicable(
        self,
        goal_formula_id: int | None = None,
        limit: int = 20,
        *,
        proof_id: int | None = None,
        arg_step_ords: Sequence[int] = (),
    ) -> list[tuple[Theorem, bool, float]]:
        if goal_formula_id is None and not arg_step_ords:
            raise ValidationError("goal_formula_id or arg_step_ords is required")
        if arg_step_ords and proof_id is None:
            raise ValidationError("proof_id is required with arg_step_ords")

        goal_tokens: list[Token] | None = None
        goal_head_id: int | None = None
        if goal_formula_id is not None:
            goal = FormulaService(self._session).get(goal_formula_id)
            if goal.formula_type.name != FormulaTypeName.PROPOSITION.value:
                raise ValidationError("goal formula must be a proposition")
            goal_tokens = self._tokens_for_formula(goal.id)
            goal_head_id = goal_tokens[0].symbol_id

        arg_formula_ids: dict[int, int] = {}
        recent_theorem_ids: frozenset[int] = frozenset()
        current_namespace_id: int | None = None
        if proof_id is not None:
            current_proof = self._session.get(Proof, proof_id)
            if current_proof is None:
                raise NotFoundError("Proof", proof_id)
            current_namespace_id = current_proof.theorem.namespace_id
            if arg_step_ords:
                arg_formula_ids = dict(
                    self._session.execute(
                        select(ProofStep.ord, ProofStep.conclusion_formula_id).where(
                            ProofStep.proof_id == proof_id,
                            ProofStep.ord.in_(set(arg_step_ords)),
                        )
                    ).all()
                )
                if any(ord_ not in arg_formula_ids for ord_ in arg_step_ords):
                    raise ValidationError(
                        "arg_step_ord must reference an existing step"
                    )
            recent_steps = (
                select(ProofStep.applied_proof_id)
                .where(ProofStep.proof_id == proof_id)
                .order_by(ProofStep.ord.desc())
                .limit(20)
                .subquery()
            )
            recent_theorem_ids = frozenset(
                self._session.scalars(
                    select(Proof.theorem_id).join(
                        recent_steps,
                        recent_steps.c.applied_proof_id == Proof.id,
                    )
                )
            )

        verified = select(Proof.id).where(
            Proof.theorem_id == Theorem.id, Proof.status == "verified"
        ).exists()
        theorem_stmt = select(Theorem).where(
            Theorem.status == "proven", verified
        )
        if goal_tokens is not None:
            schematic_heads = select(Symbol.id).join(SymbolType).where(
                SymbolType.name == SymbolTypeName.FREE_PROP_VAR.value
            )
            theorem_stmt = theorem_stmt.join(
                FormulaToken,
                and_(
                    FormulaToken.formula_id == Theorem.conclusion_formula_id,
                    FormulaToken.position == 0,
                ),
            ).where(
                or_(
                    FormulaToken.symbol_id == goal_head_id,
                    FormulaToken.symbol_id.in_(schematic_heads),
                )
            )
        theorems = list(
            self._session.scalars(theorem_stmt.order_by(Theorem.id))
        )

        theorem_ids = [theorem.id for theorem in theorems]
        premise_formula_ids: dict[int, list[int]] = {}
        if theorem_ids:
            for theorem_id, formula_id in self._session.execute(
                select(TheoremPremise.theorem_id, TheoremPremise.formula_id)
                .where(TheoremPremise.theorem_id.in_(theorem_ids))
                .order_by(TheoremPremise.theorem_id, TheoremPremise.ord)
            ):
                premise_formula_ids.setdefault(theorem_id, []).append(formula_id)

        formula_ids = {theorem.conclusion_formula_id for theorem in theorems}
        formula_ids.update(
            formula_id
            for items in premise_formula_ids.values()
            for formula_id in items
        )
        formula_ids.update(arg_formula_ids.values())
        if goal_formula_id is not None:
            formula_ids.add(goal_formula_id)
        rows = self._session.scalars(
            select(FormulaToken)
            .where(FormulaToken.formula_id.in_(formula_ids))
            .order_by(FormulaToken.formula_id, FormulaToken.position)
        )
        tokens_by_formula: dict[int, list[Token]] = {}
        for row in rows:
            tokens_by_formula.setdefault(row.formula_id, []).append(
                Token(symbol_id=row.symbol_id)
                if row.symbol_id is not None
                else Token(de_bruijn_index=row.de_bruijn_index)
            )
        arg_tokens = [
            tokens_by_formula[arg_formula_ids[ord_]] for ord_ in arg_step_ords
        ]
        all_tokens = list(goal_tokens or [])
        for tokens in tokens_by_formula.values():
            all_tokens.extend(tokens)
        symbol_meta = FormulaService(self._session)._load_symbol_meta(all_tokens)
        usage = dict(
            self._session.execute(
                select(Proof.theorem_id, func.count())
                .join(ProofStep, ProofStep.applied_proof_id == Proof.id)
                .where(Proof.theorem_id.in_(theorem_ids))
                .group_by(Proof.theorem_id)
            ).all()
        ) if theorem_ids else {}
        candidates = []
        for theorem in theorems:
            conclusion = tokens_by_formula[theorem.conclusion_formula_id]
            head = conclusion[0]
            candidates.append(
                LemmaCandidate(
                    theorem_id=theorem.id,
                    conclusion_tokens=tuple(conclusion),
                    premise_tokens=tuple(
                        tuple(tokens_by_formula[formula_id])
                        for formula_id in premise_formula_ids.get(theorem.id, [])
                    ),
                    usage_count=usage.get(theorem.id, 0),
                    namespace_id=theorem.namespace_id,
                    is_schematic=bool(
                        head.symbol_id is not None
                        and symbol_meta[head.symbol_id].symbol_type_name
                        == SymbolTypeName.FREE_PROP_VAR
                    ),
                )
            )
        ranked = rank_lemma_candidates(
            candidates,
            goal_tokens=goal_tokens,
            arg_tokens=arg_tokens,
            symbol_meta=symbol_meta,
            recent_theorem_ids=recent_theorem_ids,
            current_namespace_id=current_namespace_id,
            shared_namespace_ids=self._shared_namespace_ids(),
        )
        theorem_by_id = {theorem.id: theorem for theorem in theorems}
        return [
            (theorem_by_id[item.theorem_id], item.is_schematic, item.score)
            for item in ranked[:limit]
        ]

    def _shared_namespace_ids(self) -> frozenset[int]:
        """Namespaces every foundation shares: the logical layer."""
        logic_id = self._session.scalar(
            select(Namespace.id).where(Namespace.name == DEFAULT_NAMESPACE_NAME)
        )
        return frozenset() if logic_id is None else frozenset({logic_id})

    def _tokens_for_formula(self, formula_id: int) -> list[Token]:
        return [
            Token(symbol_id=row.symbol_id)
            if row.symbol_id is not None
            else Token(de_bruijn_index=row.de_bruijn_index)
            for row in FormulaService(self._session).get_tokens(formula_id)
        ]

    def _promote_to_proven(self, theorem_id: int) -> None:
        theorem = self.get(theorem_id)
        if theorem.status != "proven":
            theorem.status = "proven"
            self._session.flush()

    def _load_formulas(self, formula_ids: list[int]) -> dict[int, Formula]:
        unique_ids = set(formula_ids)
        if not unique_ids:
            return {}
        formulas = self._session.scalars(select(Formula).where(Formula.id.in_(unique_ids))).all()
        return {formula.id: formula for formula in formulas}
