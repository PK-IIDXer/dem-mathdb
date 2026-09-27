from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dem.db.models import Base
from dem.db.seed import seed_language
from dem.errors import ConflictError, ValidationError
from dem.services.axiom import AxiomService
from dem.services.formula import FormulaService
from dem.services.symbol import SymbolService
from dem.services.proof import ProofService
from dem.services.theorem import TheoremService
from dem.types import AxiomStepInput, SymbolTypeName, Token


def make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_language(session)
    return session


def register_prop_var(symbols: SymbolService, name: str):
    prop_type = symbols.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value)
    return symbols.register(name, prop_type.id, 0)


def register_term_var_formula(symbols: SymbolService, formulas: FormulaService):
    term_type = symbols.get_symbol_type_by_name(SymbolTypeName.FREE_TERM_VAR.value)
    x = symbols.register("x", term_type.id, 0)
    return formulas.register([Token(symbol_id=x.id)])


def register_implication_formula(
    symbols: SymbolService,
    formulas: FormulaService,
    left_symbol_id: int,
    right_symbol_id: int,
):
    implication = symbols.get_by_role("implication")
    return formulas.register(
        [Token(symbol_id=implication.id), Token(symbol_id=left_symbol_id), Token(symbol_id=right_symbol_id)]
    )


def test_register_primitive_axiom_requires_proposition_formula() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        axioms = AxiomService(session)
        term_formula = register_term_var_formula(symbols, formulas)

        with pytest.raises(ValidationError, match="axiom formula must be a proposition"):
            axioms.register("not_a_prop", term_formula.id)


def test_axiom_system_membership_and_subset() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        axioms = AxiomService(session)

        phi = register_prop_var(symbols, "φ")
        psi = register_prop_var(symbols, "ψ")
        chi = register_prop_var(symbols, "χ")

        k_formula = register_implication_formula(symbols, formulas, phi.id, psi.id)
        s_formula = register_implication_formula(symbols, formulas, psi.id, chi.id)
        k_axiom = axioms.register("K", k_formula.id)
        s_axiom = axioms.register("S", s_formula.id)

        small = axioms.register_system("small")
        large = axioms.register_system("large")
        axioms.add_to_system(small.id, k_axiom.id)
        axioms.add_to_system(large.id, k_axiom.id)
        axioms.add_to_system(large.id, s_axiom.id)

        assert [axiom.name for axiom in axioms.list_system_members(large.id)] == ["K", "S"]
        assert axioms.is_subset(small.id, large.id) is True
        assert axioms.is_subset(large.id, small.id) is False

        with pytest.raises(ConflictError):
            axioms.add_to_system(small.id, k_axiom.id)

        axioms.remove_from_system(small.id, s_axiom.id)
        assert [axiom.name for axiom in axioms.list_system_members(small.id)] == ["K"]


def test_theorem_registration_and_premise_listing() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        theorems = TheoremService(session)

        phi = register_prop_var(symbols, "φ")
        psi = register_prop_var(symbols, "ψ")
        conclusion = register_implication_formula(symbols, formulas, phi.id, psi.id)
        premise = formulas.register([Token(symbol_id=phi.id)])

        theorem = theorems.register(
            name="conditional_phi_to_psi",
            conclusion_formula_id=conclusion.id,
            premise_formula_ids=[premise.id],
        )

        assert theorem.status == "conjecture"
        premises = theorems.list_premises(theorem.id)
        assert [(ord_, formula.id) for ord_, formula in premises] == [(0, premise.id)]


def test_theorem_registration_requires_proposition_conclusion_and_premises() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        theorems = TheoremService(session)

        term_formula = register_term_var_formula(symbols, formulas)

        with pytest.raises(ValidationError, match="conclusion must be a proposition"):
            theorems.register("bad_conclusion", term_formula.id)

        phi = register_prop_var(symbols, "φ")
        prop_formula = formulas.register([Token(symbol_id=phi.id)])
        with pytest.raises(ValidationError, match="premise at index 0 must be a proposition"):
            theorems.register("bad_premise", prop_formula.id, [term_formula.id])


def _verified_theorem(session):
    """A theorem with a verified proof, the only way to reach 'proven'."""
    symbols = SymbolService(session)
    formulas = FormulaService(session)
    theorems = TheoremService(session)
    axioms = AxiomService(session)
    proofs = ProofService(session)

    phi = register_prop_var(symbols, "φ")
    formula = formulas.register([Token(symbol_id=phi.id)])
    theorem = theorems.register("phi", formula.id)
    axiom = axioms.register("phi_axiom", formula.id)
    proof = proofs.create_proof(theorem.id)
    proofs.add_step(proof.id, AxiomStepInput(axiom.id), formula.id)
    proofs.validate(proof.id)
    return theorems, theorem


def test_promote_to_proven_is_idempotent() -> None:
    with make_session() as session:
        theorems, theorem = _verified_theorem(session)

        theorems._promote_to_proven(theorem.id)
        theorems._promote_to_proven(theorem.id)

        assert theorems.get(theorem.id).status == "proven"


def test_a_theorem_without_a_verified_proof_cannot_be_promoted() -> None:
    """The D7 guard (lean-import-design §3.7): 'proven' means a verified proof
    exists, and the database now holds that, not only the services."""
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        theorems = TheoremService(session)

        phi = register_prop_var(symbols, "φ")
        formula = formulas.register([Token(symbol_id=phi.id)])
        theorem = theorems.register("phi", formula.id)

        with pytest.raises(IntegrityError, match="a theorem can only be proven"):
            theorems._promote_to_proven(theorem.id)
