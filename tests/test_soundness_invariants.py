"""Soundness invariants for the minimal meta-kernel (design doc §8).

These pin, as regressions, the trust-boundary guarantees that are *confirmed*
rather than proved as object-level theorems:

- A proof becomes ``verified`` only inside ``ProofService.validate()`` — there
  is no discharge/builder path that marks a proof verified directly (§8: the
  ``discharge()`` output and every builder/generator output is re-checked by
  the raw kernel; builder output is never trusted unconditionally).
- ``theorem`` steps apply a *verified* theorem under uniform substitution, and
  the kernel re-applies the substitution against the pinned theorem data rather
  than trusting the builder (§8: theorem-application uniform-substitution
  meta-theorem, traceable to these cases).
- **Invariant (E)** (§9.4): every proof using ``implication_intro`` can be
  rewritten by ``expand_implication_intro()`` into one that uses MP and Gen
  only, and the rewrite is accepted by the kernel. This is what keeps
  ⇒introduction from widening the trust boundary: it is admissible, not
  primitive, and the elimination procedure is its evidence. A local
  ``assumption`` may never survive into a theorem's conclusion.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dem.db.models import Base
from dem.db.seed import seed_inference_rules, seed_language
from dem.db.seeds.hilbert import seed_hilbert_core
from dem.db.seeds.hilbert_toolkit import (
    DischargeStep,
    HilbertToolkit,
)
from dem.errors import ProofValidationError
from dem.services.axiom import AxiomService
from dem.services.formula import FormulaService
from dem.services.proof import ProofService
from dem.services.symbol import SymbolService
from dem.services.theorem import TheoremService
from dem.types import (
    AssumptionStepInput,
    AxiomStepInput,
    PropSubst,
    Substitution,
    SymbolTypeName,
    TheoremStepInput,
    Token,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
DEM_ROOT = REPO_ROOT / "dem"


def _dem_py_files() -> list[Path]:
    return [p for p in DEM_ROOT.rglob("*.py") if "__pycache__" not in p.parts]


_RAW_SQL_VERIFIED_UPDATE = re.compile(
    r"\bUPDATE\s+(?:[A-Za-z_][A-Za-z0-9_]*\.)?[\"`\[]?proof[\"`\]]?\s+"
    r"SET\b(?:(?!\bWHERE\b|;).)*\bstatus\s*=\s*(['\"])verified\1",
    re.IGNORECASE | re.DOTALL,
)
_RAW_SQL_VERIFIED_INSERT = re.compile(
    r"\bINSERT\s+INTO\s+(?:[A-Za-z_][A-Za-z0-9_]*\.)?[\"`\[]?proof[\"`\]]?"
    r"\s*\([^)]*\bstatus\b[^)]*\)\s*VALUES\s*\([^)]*(['\"])verified\1[^)]*\)",
    re.IGNORECASE | re.DOTALL,
)


class _VerifiedStatusWriterVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.scope: list[str] = []
        self.assignments: list[tuple[str, int, tuple[str, ...], str]] = []
        self.raw_sql: list[tuple[str, int]] = []
        # ORM / Core expressions: `Proof(status="verified")`,
        # `update(Proof).values(status="verified")`, `{"status": "verified"}`.
        self.expression_writes: list[tuple[str, int]] = []

    def _relative_path(self) -> str:
        return self.path.relative_to(REPO_ROOT).as_posix()

    @staticmethod
    def _is_verified(node: ast.AST | None) -> bool:
        return isinstance(node, ast.Constant) and node.value == "verified"

    def _record_assignment(self, node: ast.AST, kind: str) -> None:
        self.assignments.append(
            (self._relative_path(), node.lineno, tuple(self.scope), kind)
        )

    def _visit_scoped(self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_scoped(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_scoped(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_scoped(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._is_verified(node.value) and any(
            isinstance(candidate, ast.Attribute) and candidate.attr == "status"
            for target in node.targets
            for candidate in ast.walk(target)
        ):
            self._record_assignment(node, "assignment")
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if self._is_verified(node.value) and any(
            isinstance(candidate, ast.Attribute) and candidate.attr == "status"
            for candidate in ast.walk(node.target)
        ):
            self._record_assignment(node, "annotated assignment")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "setattr"
            and len(node.args) >= 3
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value == "status"
            and self._is_verified(node.args[2])
        ):
            self._record_assignment(node, "setattr")
        if any(
            keyword.arg == "status" and self._is_verified(keyword.value)
            for keyword in node.keywords
        ):
            self.expression_writes.append((self._relative_path(), node.lineno))
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        if any(
            isinstance(key, ast.Constant)
            and key.value == "status"
            and self._is_verified(value)
            for key, value in zip(node.keys, node.values)
        ):
            self.expression_writes.append((self._relative_path(), node.lineno))
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and (
            _RAW_SQL_VERIFIED_UPDATE.search(node.value)
            or _RAW_SQL_VERIFIED_INSERT.search(node.value)
        ):
            self.raw_sql.append((self._relative_path(), node.lineno))


# -- static invariants -----------------------------------------------------


def test_only_proof_service_validate_assigns_verified_proof_status() -> None:
    """A proof's status is set to ``"verified"`` in exactly one place — inside
    ``ProofService.validate()``. Nothing (discharge, seed generators, builders)
    may bypass the kernel by marking a proof verified directly.
    """
    assignments: list[tuple[str, int, tuple[str, ...], str]] = []
    raw_sql: list[tuple[str, int]] = []
    expression_writes: list[tuple[str, int]] = []
    for path in _dem_py_files():
        visitor = _VerifiedStatusWriterVisitor(path)
        visitor.visit(ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path)))
        assignments.extend(visitor.assignments)
        raw_sql.extend(visitor.raw_sql)
        expression_writes.extend(visitor.expression_writes)

    assert raw_sql == [], f"raw SQL may not mark a proof verified: {raw_sql}"
    assert expression_writes == [], (
        f"ORM/Core expressions may not mark a proof verified: {expression_writes}"
    )
    assert len(assignments) == 1, (
        f"expected a single verified-status writer, found: {assignments}"
    )
    path, _lineno, scope, _kind = assignments[0]
    assert path == "dem/services/proof.py", assignments
    assert scope == ("ProofService", "validate"), assignments


# -- runtime invariants ----------------------------------------------------


def _make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_language(session)
    seed_inference_rules(session)
    return session


def _prop_var(symbols: SymbolService, name: str):
    prop_type = symbols.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value)
    return symbols.register(name, prop_type.id, 0)


def test_raw_steps_leave_proof_draft_until_validate() -> None:
    """``add_raw_steps`` persists steps but does not verify — the proof is
    ``draft`` until ``validate()`` re-checks it."""
    with _make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        axioms = AxiomService(session)
        theorems = TheoremService(session)
        proofs = ProofService(session)

        phi = _prop_var(symbols, "phi_draft")
        body = formulas.register([Token(symbol_id=phi.id)])
        axiom = axioms.register("phi_draft_axiom", body.id)
        theorem = theorems.register("phi_draft_theorem", body.id)
        proof = proofs.create_proof(theorem.id)

        proofs.add_raw_steps(proof.id, [(AxiomStepInput(axiom.id), body.id)])
        assert proofs.get(proof.id).status == "draft"

        proofs.validate(proof.id)
        assert proofs.get(proof.id).status == "verified"


def test_validate_rejects_proof_that_does_not_establish_the_goal() -> None:
    """The kernel re-derives each step's conclusion and checks it against the
    goal; a proof whose steps do not actually establish the theorem is rejected
    (the builder-supplied conclusion is never trusted on its own)."""
    with _make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        axioms = AxiomService(session)
        theorems = TheoremService(session)
        proofs = ProofService(session)

        phi = _prop_var(symbols, "phi_goal")
        psi = _prop_var(symbols, "psi_goal")
        phi_body = formulas.register([Token(symbol_id=phi.id)])
        psi_body = formulas.register([Token(symbol_id=psi.id)])
        axiom = axioms.register("phi_goal_axiom", phi_body.id)
        # The theorem claims ψ, but the only step derives φ.
        theorem = theorems.register("psi_goal_theorem", psi_body.id)
        proof = proofs.create_proof(theorem.id)
        proofs.add_raw_steps(proof.id, [(AxiomStepInput(axiom.id), phi_body.id)])

        with pytest.raises(ProofValidationError):
            proofs.validate(proof.id)
        assert proofs.get(proof.id).status == "rejected"


def test_theorem_application_uniform_substitution_validates() -> None:
    """A verified theorem may be applied under uniform propositional
    substitution; the kernel re-applies the substitution to the pinned theorem
    conclusion (φ ⟼ ψ) and accepts the instantiated result."""
    with _make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        axioms = AxiomService(session)
        theorems = TheoremService(session)
        proofs = ProofService(session)

        phi = _prop_var(symbols, "phi_app")
        psi = _prop_var(symbols, "psi_app")
        phi_body = formulas.register([Token(symbol_id=phi.id)])
        psi_body = formulas.register([Token(symbol_id=psi.id)])

        # Verified theorem T : φ.
        axiom = axioms.register("phi_app_axiom", phi_body.id)
        theorem_t = theorems.register("phi_app_theorem", phi_body.id)
        proof_t = proofs.create_proof(theorem_t.id)
        proofs.add_step(proof_t.id, AxiomStepInput(axiom.id), phi_body.id)
        proofs.validate(proof_t.id)
        assert proofs.get(proof_t.id).status == "verified"

        # Theorem T2 : ψ, proved by applying T under φ ⟼ ψ.
        theorem_t2 = theorems.register("psi_app_theorem", psi_body.id)
        proof_t2 = proofs.create_proof(theorem_t2.id)
        subst = Substitution(prop_substs=(PropSubst(phi.id, psi_body.id),))
        proofs.add_step(proof_t2.id, TheoremStepInput(proof_t.id, subst), psi_body.id)
        proofs.validate(proof_t2.id)
        assert proofs.get(proof_t2.id).status == "verified"


def _hilbert_session() -> Session:
    session = _make_session()
    seed_hilbert_core(session)
    return session


def _hypothetical_syllogism_derivation(
    toolkit: HilbertToolkit,
) -> tuple[list[DischargeStep], list[Token]]:
    """`[φ→ψ, ψ→χ] ⊢ φ→χ` from K and S -- the smallest derivation whose two
    premises are worth discharging."""
    phi = toolkit.atom(toolkit.phi)
    psi = toolkit.atom(toolkit.psi)
    chi = toolkit.atom(toolkit.chi)
    phi_to_psi = toolkit.imp(phi, psi)
    psi_to_chi = toolkit.imp(psi, chi)
    phi_to_chi = toolkit.imp(phi, chi)

    k_axiom = toolkit.axioms.get_by_name("hilbert_k")
    s_axiom = toolkit.axioms.get_by_name("hilbert_s")
    sigma_k = Substitution(
        prop_substs=(
            PropSubst(toolkit.phi.id, toolkit._formula(psi_to_chi).id),
            PropSubst(toolkit.psi.id, toolkit._formula(phi).id),
        )
    )
    steps = [
        DischargeStep(kind="premise", tokens=phi_to_psi, premise_index=0),
        DischargeStep(kind="premise", tokens=psi_to_chi, premise_index=1),
        DischargeStep(
            kind="fact",
            tokens=toolkit.proofs.compute_substituted_tokens(k_axiom.formula_id, sigma_k),
            fact_input=AxiomStepInput(k_axiom.id, sigma_k),
        ),
        DischargeStep(kind="mp", tokens=toolkit.imp(phi, psi_to_chi), mp_left=1, mp_right=2),
        DischargeStep(
            kind="fact",
            tokens=toolkit.imp(
                toolkit.imp(phi, psi_to_chi), toolkit.imp(phi_to_psi, phi_to_chi)
            ),
            fact_input=AxiomStepInput(s_axiom.id),
        ),
        DischargeStep(
            kind="mp", tokens=toolkit.imp(phi_to_psi, phi_to_chi), mp_left=3, mp_right=4
        ),
        DischargeStep(kind="mp", tokens=phi_to_chi, mp_left=0, mp_right=5),
    ]
    target = toolkit.imp(phi_to_psi, toolkit.imp(psi_to_chi, phi_to_chi))
    return steps, target


def test_implication_intro_proof_expands_to_an_mp_and_gen_proof() -> None:
    """Invariant (E), design doc §9.4.

    The same theorem is proved twice from the same derivation: once with
    ⇒introduction, once after ``expand_implication_intro()`` has rewritten the
    ⇒intros away. Both are checked by the kernel, and the expanded one contains
    no ``assumption`` or ``implication_intro`` step at all -- so admitting
    ⇒introduction proves nothing that MP and Gen alone could not.
    """
    with _hilbert_session() as session:
        toolkit = HilbertToolkit(session)
        proofs = ProofService(session)
        original, target = _hypothetical_syllogism_derivation(toolkit)

        with_intro = toolkit.discharge(original, 1, original[1].tokens)
        with_intro = toolkit.discharge(with_intro, 0, original[0].tokens)
        assert with_intro[-1].tokens == target
        assert {step.kind for step in with_intro} >= {"assumption", "imp_intro"}

        expanded = toolkit.expand_implication_intro(with_intro)
        assert expanded[-1].tokens == target
        assert {step.kind for step in expanded} & {"assumption", "imp_intro"} == set()

        intro_theorem = toolkit._get_or_create_theorem("invariant_e_with_intro", target, [])
        intro_proof = toolkit._prove(intro_theorem, toolkit.to_proof_step_specs(with_intro))
        assert intro_proof.status == "verified"

        expanded_theorem = toolkit._get_or_create_theorem(
            "invariant_e_expanded", target, []
        )
        expanded_proof = toolkit._prove(
            expanded_theorem, toolkit.to_proof_step_specs(expanded)
        )
        assert expanded_proof.status == "verified"

        # And the expansion is what costs: that ratio is the whole of §9.1.
        assert len(proofs.list_steps(expanded_proof.id)) > len(
            proofs.list_steps(intro_proof.id)
        )


def test_implication_intro_expansion_preserves_pre_assumption_premise_for_tail() -> None:
    """A tail step after ⇒intro may still cite a theorem premise introduced
    before the local assumption. Expansion must preserve that premise as ``P``;
    replacing the reference with its K-lifted ``A -> P`` changes the MP input.
    """
    with _hilbert_session() as session:
        toolkit = HilbertToolkit(session)
        phi = toolkit.atom(toolkit.phi)
        psi = toolkit.atom(toolkit.psi)
        phi_to_phi = toolkit.imp(phi, phi)
        identity_formula = toolkit._formula(phi_to_phi)
        identity_axiom = toolkit.axioms.register(
            "test_identity_tail_axiom", identity_formula.id
        )
        steps = [
            DischargeStep(kind="premise", tokens=phi, premise_index=0),
            DischargeStep(kind="assumption", tokens=psi),
            DischargeStep(kind="premise", tokens=phi, premise_index=0),
            DischargeStep(
                kind="imp_intro",
                tokens=toolkit.imp(psi, phi),
                imp_assumption_ord=1,
                imp_body_ord=2,
            ),
            DischargeStep(
                kind="fact",
                tokens=phi_to_phi,
                fact_input=AxiomStepInput(identity_axiom.id),
            ),
            DischargeStep(kind="mp", tokens=phi, mp_left=0, mp_right=4),
        ]

        expanded = toolkit.expand_implication_intro(steps)
        assert {step.kind for step in expanded} & {"assumption", "imp_intro"} == set()
        theorem = toolkit._get_or_create_theorem(
            "invariant_e_tail_premise",
            phi,
            [phi],
        )
        proof = toolkit._prove(theorem, toolkit.to_proof_step_specs(expanded))
        assert proof.status == "verified"


def test_implication_intro_expands_nested_equal_assumptions_as_vacuous_outer_intro() -> None:
    """The kernel identifies assumptions by formula, so the inner discharge of
    A also clears an equal outer A. The remaining outer ⇒intro is vacuous and
    its elimination is the K instance ``B -> (A -> B)``.
    """
    with _hilbert_session() as session:
        toolkit = HilbertToolkit(session)
        phi = toolkit.atom(toolkit.phi)
        phi_to_phi = toolkit.imp(phi, phi)
        target = toolkit.imp(phi, phi_to_phi)
        steps = [
            DischargeStep(kind="assumption", tokens=phi),
            DischargeStep(kind="assumption", tokens=phi),
            DischargeStep(
                kind="imp_intro",
                tokens=phi_to_phi,
                imp_assumption_ord=1,
                imp_body_ord=1,
            ),
            DischargeStep(
                kind="imp_intro",
                tokens=target,
                imp_assumption_ord=0,
                imp_body_ord=2,
            ),
        ]
        expanded = toolkit.expand_implication_intro(steps)
        assert expanded[-1].tokens == target
        assert {step.kind for step in expanded} & {"assumption", "imp_intro"} == set()
        theorem = toolkit._get_or_create_theorem(
            "invariant_e_nested_equal_assumptions",
            target,
            [],
        )
        proof = toolkit._prove(theorem, toolkit.to_proof_step_specs(expanded))
        assert proof.status == "verified"


def test_implication_intro_expansion_lifts_independent_gen_after_assumption() -> None:
    """An independent Gen can survive discharge even when the discharged
    assumption contains the generalized variable.  Expansion must Gen the
    independent body first and K-lift that result; Gen on ``A(x) -> B`` would
    violate the kernel's eigenvariable side condition.
    """
    with _hilbert_session() as session:
        toolkit = HilbertToolkit(session)
        phi = toolkit.atom(toolkit.phi)
        phi_to_phi = toolkit.imp(phi, phi)
        x = toolkit.symbols.get_by_name("x")
        phi1 = toolkit.symbols.get_by_name("φ¹")
        assumption = [Token(symbol_id=phi1.id), Token(symbol_id=x.id)]

        identity_formula = toolkit._formula(phi_to_phi)
        identity_axiom = toolkit.axioms.register(
            "test_identity_gen_axiom", identity_formula.id
        )
        generalized = toolkit.proofs.compute_gen_tokens(
            toolkit._formula(phi_to_phi).id, x.id
        )
        target = toolkit.imp(assumption, generalized)
        steps = [
            DischargeStep(kind="assumption", tokens=assumption),
            DischargeStep(
                kind="fact",
                tokens=phi_to_phi,
                fact_input=AxiomStepInput(identity_axiom.id),
            ),
            DischargeStep(
                kind="gen",
                tokens=generalized,
                gen_body_ord=1,
                gen_variable_symbol_id=x.id,
            ),
            DischargeStep(
                kind="imp_intro",
                tokens=target,
                imp_assumption_ord=0,
                imp_body_ord=2,
            ),
        ]

        expanded = toolkit.expand_implication_intro(steps)
        assert expanded[-1].tokens == target
        assert {step.kind for step in expanded} & {"assumption", "imp_intro"} == set()
        theorem = toolkit._get_or_create_theorem(
            "invariant_e_independent_gen_after_assumption",
            target,
            [],
        )
        proof = toolkit._prove(theorem, toolkit.to_proof_step_specs(expanded))
        assert proof.status == "verified"


def test_vacuous_implication_intro_is_accepted() -> None:
    """Discharging an assumption that was never used is sound -- it is exactly
    what ``hilbert_k`` says -- so the kernel does not require the discharged
    formula to occur in the body's dependencies."""
    with _hilbert_session() as session:
        toolkit = HilbertToolkit(session)
        phi = toolkit.atom(toolkit.phi)
        psi = toolkit.atom(toolkit.psi)
        psi_to_psi = toolkit.imp(psi, psi)
        identity_formula = toolkit._formula(psi_to_psi)
        identity_axiom = toolkit.axioms.register(
            "test_identity_vacuous_axiom", identity_formula.id
        )
        original = [
            DischargeStep(kind="premise", tokens=phi, premise_index=0),
            DischargeStep(
                kind="fact",
                tokens=psi_to_psi,
                fact_input=AxiomStepInput(identity_axiom.id),
            ),
        ]
        closed = toolkit.discharge(original, 0, phi)
        target = toolkit.imp(phi, toolkit.imp(psi, psi))
        assert closed[-1].tokens == target

        theorem = toolkit._get_or_create_theorem("vacuous_intro", target, [])
        proof = toolkit._prove(theorem, toolkit.to_proof_step_specs(closed))
        assert proof.status == "verified"


def test_undischarged_assumption_is_rejected() -> None:
    """An assumption pays for itself only through ⇒introduction. A proof whose
    conclusion still depends on one would be proving the theorem from a
    hypothesis the theorem never declared, so the kernel rejects it."""
    with _make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        theorems = TheoremService(session)
        proofs = ProofService(session)

        phi = _prop_var(symbols, "phi_open")
        body = formulas.register([Token(symbol_id=phi.id)])
        theorem = theorems.register("phi_open_theorem", body.id)
        proof = proofs.create_proof(theorem.id)
        proofs.add_raw_steps(proof.id, [(AssumptionStepInput(), body.id)])

        with pytest.raises(ProofValidationError, match="undischarged assumption"):
            proofs.validate(proof.id)
        assert proofs.get(proof.id).status == "rejected"


def test_theorem_application_of_unverified_proof_is_rejected() -> None:
    """Applying a proof that has not itself been verified is rejected — a
    theorem step may only cite a verified proof."""
    with _make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        axioms = AxiomService(session)
        theorems = TheoremService(session)
        proofs = ProofService(session)

        phi = _prop_var(symbols, "phi_unv")
        phi_body = formulas.register([Token(symbol_id=phi.id)])
        axioms.register("phi_unv_axiom", phi_body.id)

        # Draft (unverified) proof of φ.
        theorem_t = theorems.register("phi_unv_theorem", phi_body.id)
        draft_proof = proofs.create_proof(theorem_t.id)

        # Another proof cites the draft proof.
        theorem_t2 = theorems.register("phi_unv_theorem2", phi_body.id)
        proof_t2 = proofs.create_proof(theorem_t2.id)
        with pytest.raises(ProofValidationError, match="unverified") as error:
            proofs.add_step(proof_t2.id, TheoremStepInput(draft_proof.id, Substitution()), phi_body.id)
        assert error.value.code == "proof.unverified_citation"
        assert proofs.list_steps(proof_t2.id) == []
        assert proofs.get(proof_t2.id).status == "draft"
        proofs.add_raw_steps(proof_t2.id, [(TheoremStepInput(draft_proof.id, Substitution()), phi_body.id)])
        with pytest.raises(ProofValidationError, match="unverified"):
            proofs.validate(proof_t2.id)
        assert proofs.get(proof_t2.id).status == "rejected"
