from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dem.db.models.inference import Axiom
from dem.db.models.language import Formula, Namespace, Symbol
from dem.db.models.tag import Tag, TheoremTag
from dem.db.models.theorem import Proof, ProofStep, ProofStepArg, Theorem
from dem.errors import NotFoundError, ProofValidationError, ValidationError
from dem.identity import DEFAULT_NAMESPACE_NAME
from dem.services.authoring_provenance import AuthoringVia
from dem.services.formula import FormulaService
from dem.services.proof import ProofService
from dem.services.system_tags import EXPLORATION_TAG
from dem.services.tag import TagService
from dem.services.theorem import TheoremService
from dem.services.used_axioms import used_axiom_ids_for_dependencies
from dem.types import (
    AssumptionStepInput,
    AxiomStepInput,
    GenStepInput,
    ImplicationIntroStepInput,
    MPStepInput,
    PremiseStepInput,
    ProofStepInput,
    TheoremStepInput,
    Token,
)


@dataclass(frozen=True)
class ExplorationNote:
    theorem: Theorem
    proof: Proof
    premises: tuple[Formula, ...]
    step_count: int
    updated_at: datetime


@dataclass(frozen=True)
class ExplorationDependencies:
    axioms: tuple[Axiom, ...]
    theorems: tuple[Theorem, ...]


@dataclass(frozen=True)
class ExplorationPromotion:
    theorem: Theorem
    proof: Proof


class ExplorationService:
    """Application service for hidden, goal-free inference notebooks.

    The storage is deliberately ordinary theorem/proof storage.  A note is a
    tagged conjecture with the harmless logical-core conclusion ``¬⊥`` and
    one draft proof.  Every appended line therefore crosses the exact same
    ``ProofService.add_step`` and database boundaries as any other draft.
    """

    def __init__(
        self,
        session: Session,
        *,
        authoring_via: AuthoringVia | None = None,
    ) -> None:
        self._session = session
        self._authoring_via = authoring_via

    def create(
        self,
        name: str,
        premise_formula_ids: list[int] | None = None,
        *,
        namespace: str = DEFAULT_NAMESPACE_NAME,
    ) -> ExplorationNote:
        truth = self._logical_truth_formula()
        theorem = self._theorems.register(
            name=name,
            conclusion_formula_id=truth.id,
            premise_formula_ids=premise_formula_ids or [],
            namespace=namespace,
        )
        tag = TagService(self._session).get_or_create(EXPLORATION_TAG)
        TagService(self._session).attach("theorem", theorem.id, tag.id)
        proof = self._proofs.create_proof(theorem.id, name=name)
        return self._note(theorem, proof)

    def list_all(self) -> list[ExplorationNote]:
        rows = self._session.execute(
            select(Theorem, Proof)
            .join(TheoremTag, TheoremTag.theorem_id == Theorem.id)
            .join(Tag, Tag.id == TheoremTag.tag_id)
            .join(Proof, Proof.theorem_id == Theorem.id)
            .where(
                Tag.name == EXPLORATION_TAG,
                Proof.status == "draft",
                Proof.identity_ordinal == 0,
            )
            .order_by(Theorem.id)
        ).all()
        return [self._note(theorem, proof) for theorem, proof in rows]

    def get(self, ref: int | str) -> ExplorationNote:
        theorem = (
            self._theorems.get(int(ref))
            if isinstance(ref, int) or ref.isdigit()
            else self._theorems.get_by_public_id(ref)
        )
        if not self._is_exploration(theorem.id):
            raise NotFoundError("Exploration", ref)
        proof = self._session.scalar(
            select(Proof)
            .where(Proof.theorem_id == theorem.id, Proof.status == "draft")
            .order_by(Proof.identity_ordinal)
            .limit(1)
        )
        if proof is None:
            raise NotFoundError("Exploration proof", ref)
        return self._note(theorem, proof)

    def list_line_dependencies(
        self, ref: int | str, step_ord: int
    ) -> ExplorationDependencies:
        note = self.get(ref)
        ancestors = self._ancestor_ords(note.proof.id, step_ord)
        rows = list(
            self._session.scalars(
                select(ProofStep)
                .where(
                    ProofStep.proof_id == note.proof.id,
                    ProofStep.ord.in_(ancestors),
                )
                .order_by(ProofStep.ord)
            )
        )
        direct_axiom_ids = {
            step.axiom_id for step in rows if step.axiom_id is not None
        }
        applied_proof_ids: dict[int, None] = {}
        for step in rows:
            if step.applied_proof_id is not None:
                applied_proof_ids.setdefault(step.applied_proof_id)

        axiom_ids = used_axiom_ids_for_dependencies(
            self._session,
            direct_axiom_ids=direct_axiom_ids,
            applied_proof_ids=applied_proof_ids,
        )
        axioms = tuple(
            self._session.scalars(
                select(Axiom).where(Axiom.id.in_(axiom_ids)).order_by(Axiom.id)
            )
        ) if axiom_ids else ()

        proofs = {
            proof.id: proof
            for proof in self._session.scalars(
                select(Proof).where(Proof.id.in_(applied_proof_ids))
            )
        }
        cited: list[Theorem] = []
        seen_theorem_ids: set[int] = set()
        for proof_id in applied_proof_ids:
            proof = proofs[proof_id]
            if proof.theorem_id not in seen_theorem_ids:
                cited.append(proof.theorem)
                seen_theorem_ids.add(proof.theorem_id)
        return ExplorationDependencies(axioms=axioms, theorems=tuple(cited))

    def contains_proof(self, proof_id: int) -> bool:
        """Whether ``proof_id`` is the hidden draft owned by a note."""
        return bool(
            self._session.scalar(
                select(Proof.id)
                .join(TheoremTag, TheoremTag.theorem_id == Proof.theorem_id)
                .join(Tag, Tag.id == TheoremTag.tag_id)
                .where(Proof.id == proof_id, Tag.name == EXPLORATION_TAG)
            )
        )

    def promote(
        self,
        ref: int | str,
        step_ord: int,
        name: str,
        *,
        namespace: str | None = None,
    ) -> ExplorationPromotion:
        note = self.get(ref)
        steps = self._proofs.list_steps(note.proof.id)
        by_ord = {step.ord: step for step in steps}
        if step_ord not in by_ord:
            raise NotFoundError("ProofStep", f"{note.proof.id}:{step_ord}")

        next_ord = steps[-1].ord + 1 if steps else 0
        prefix = self._proofs._prior_judgements(note.proof, next_ord)
        selected = prefix.prior[step_ord]
        if any(kind == "assumption" for kind, _ in selected.premise_deps):
            raise ValidationError(
                "selected line depends on an undischarged assumption",
                code="exploration.open_assumption",
                details={"step_ord": step_ord},
            )

        ancestors = self._ancestor_ords(note.proof.id, step_ord)
        ordered_ords = sorted(ancestors)
        old_to_new = {old: new for new, old in enumerate(ordered_ords)}
        premise_ords = sorted(
            {
                by_ord[old].premise_ord
                for old in ordered_ords
                if by_ord[old].premise_ord is not None
            }
        )
        premise_map = {old: new for new, old in enumerate(premise_ords)}
        premises = {
            ord_: formula
            for ord_, formula in self._theorems.list_premises(note.theorem.id)
        }
        reconstructed = self._proofs.reconstruct_steps(note.proof.id)

        try:
            with self._session.begin_nested():
                theorem = self._theorems.register(
                    name=name,
                    conclusion_formula_id=by_ord[step_ord].conclusion_formula_id,
                    premise_formula_ids=[premises[ord_].id for ord_ in premise_ords],
                    namespace=namespace or DEFAULT_NAMESPACE_NAME,
                    namespace_id=(
                        note.theorem.namespace_id if namespace is None else None
                    ),
                )
                proof = self._proofs.create_proof(theorem.id, name=name)
                for old_ord in ordered_ords:
                    step_input, _ = reconstructed[old_ord]
                    remapped = _remap_step_input(step_input, old_to_new, premise_map)
                    self._proofs.add_step(
                        proof.id,
                        remapped,
                        by_ord[old_ord].conclusion_formula_id,
                    )
                self._proofs.validate(proof.id)
                if proof.status != "verified":
                    raise ProofValidationError(
                        "promoted proof was not verified",
                        code="exploration.promotion_not_verified",
                    )
        except ProofValidationError as exc:
            raise ValidationError(
                "selected line could not be promoted to a verified theorem",
                code="exploration.promotion_validation_failed",
                details={"proof_code": exc.code, "step_ord": exc.step_ord},
            ) from exc
        return ExplorationPromotion(theorem=theorem, proof=proof)

    @property
    def _theorems(self) -> TheoremService:
        return TheoremService(self._session, authoring_via=self._authoring_via)

    @property
    def _proofs(self) -> ProofService:
        return ProofService(self._session, authoring_via=self._authoring_via)

    def _logical_truth_formula(self) -> Formula:
        symbols = dict(
            self._session.execute(
                select(Symbol.name, Symbol)
                .join(Namespace, Namespace.id == Symbol.namespace_id)
                .where(
                    Namespace.name == DEFAULT_NAMESPACE_NAME,
                    Symbol.name.in_(("¬", "⊥")),
                )
            ).all()
        )
        for name in ("¬", "⊥"):
            if name not in symbols:
                raise NotFoundError("logical core symbol", name)
        return FormulaService(
            self._session, authoring_via=self._authoring_via
        ).register(
            [Token(symbol_id=symbols["¬"].id), Token(symbol_id=symbols["⊥"].id)]
        )

    def _is_exploration(self, theorem_id: int) -> bool:
        return bool(
            self._session.scalar(
                select(TheoremTag.theorem_id)
                .join(Tag, Tag.id == TheoremTag.tag_id)
                .where(
                    TheoremTag.theorem_id == theorem_id,
                    Tag.name == EXPLORATION_TAG,
                )
            )
        )

    def _note(self, theorem: Theorem, proof: Proof) -> ExplorationNote:
        premises = tuple(formula for _, formula in self._theorems.list_premises(theorem.id))
        step_count = int(
            self._session.scalar(
                select(func.count()).select_from(ProofStep).where(ProofStep.proof_id == proof.id)
            )
            or 0
        )
        last_step = self._session.scalar(
            select(func.max(ProofStep.created_at)).where(ProofStep.proof_id == proof.id)
        )
        updated_at = max(
            value for value in (theorem.updated_at, proof.updated_at, last_step) if value is not None
        )
        return ExplorationNote(theorem, proof, premises, step_count, updated_at)

    def _ancestor_ords(self, proof_id: int, step_ord: int) -> set[int]:
        if self._session.get(ProofStep, {"proof_id": proof_id, "ord": step_ord}) is None:
            raise NotFoundError("ProofStep", f"{proof_id}:{step_ord}")
        args: dict[int, list[int]] = {}
        for row in self._session.scalars(
            select(ProofStepArg)
            .where(ProofStepArg.proof_id == proof_id)
            .order_by(ProofStepArg.step_ord, ProofStepArg.arg_ord)
        ):
            args.setdefault(row.step_ord, []).append(row.referenced_step_ord)
        ancestors: set[int] = set()
        frontier = [step_ord]
        while frontier:
            current = frontier.pop()
            if current in ancestors:
                continue
            ancestors.add(current)
            frontier.extend(args.get(current, ()))
        return ancestors


def _remap_step_input(
    step: ProofStepInput,
    ord_map: dict[int, int],
    premise_map: dict[int, int],
) -> ProofStepInput:
    if isinstance(step, PremiseStepInput):
        return PremiseStepInput(premise_map[step.premise_ord])
    if isinstance(step, AssumptionStepInput):
        return step
    if isinstance(step, AxiomStepInput):
        return step
    if isinstance(step, TheoremStepInput):
        return TheoremStepInput(
            step.applied_proof_id,
            step.subst,
            tuple(ord_map[ord_] for ord_ in step.arg_step_ords),
        )
    if isinstance(step, MPStepInput):
        return MPStepInput(
            ord_map[step.antecedent_step_ord],
            ord_map[step.implication_step_ord],
        )
    if isinstance(step, GenStepInput):
        return GenStepInput(
            ord_map[step.body_step_ord], step.gen_variable_symbol_id
        )
    if isinstance(step, ImplicationIntroStepInput):
        return ImplicationIntroStepInput(
            ord_map[step.assumption_step_ord], ord_map[step.body_step_ord]
        )
    raise TypeError(f"unsupported proof step input: {type(step)!r}")
