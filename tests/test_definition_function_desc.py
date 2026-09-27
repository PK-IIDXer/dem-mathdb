from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dem.db.models import Base
from dem.db.seed import seed_inference_rules, seed_language
from dem.db.seeds.hilbert import seed_hilbert_core
from dem.errors import ValidationError
from dem.services.definition import DefinitionService
from dem.services.formula import FormulaService
from dem.services.proof import ProofService
from dem.services.symbol import SymbolService
from dem.services.theorem import TheoremService
from dem.types import (
    DescriptiveFunctionDefinitionInput,
    PremiseStepInput,
    SymbolTypeName,
    Token,
)


def make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_language(session)
    seed_inference_rules(session)
    seed_hilbert_core(session)
    return session


def register_term_var(symbols: SymbolService, name: str):
    term_type = symbols.get_symbol_type_by_name(SymbolTypeName.FREE_TERM_VAR.value)
    return symbols.register(name, term_type.id, 0)


def formula_tokens(formulas: FormulaService, formula_id: int) -> list[Token]:
    return [
        Token(symbol_id=row.symbol_id, de_bruijn_index=row.de_bruijn_index)
        for row in formulas.get_tokens(formula_id)
    ]


def test_register_explicit_function_with_params_closes_over_each_one() -> None:
    """A 1-arity explicit function id(x) := x, exercising the Gen-over-params
    loop (the zero-arity test in test_phase4_definition_service.py doesn't
    reach it)."""
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        definitions = DefinitionService(session)

        x = register_term_var(symbols, "identity_param")
        body = formulas.register([Token(symbol_id=x.id)])

        definition = definitions.register_explicit_function(
            name="identity_like",
            param_symbol_ids=(x.id,),
            body_term_formula_id=body.id,
        )

        new_symbol = definitions.get_symbol(definition.id)
        assert new_symbol.arity == 1
        assert [s.id for s in definitions.list_formal_params(definition.id)] == [x.id]
        assert definition.display_formula is not None
        assert formula_tokens(formulas, definition.display_formula.id) == [
            Token(symbol_id=symbols.get_by_role("universal_quantifier").id),
            Token(symbol_id=symbols.get_by_role("equality").id),
            Token(symbol_id=new_symbol.id),
            Token(de_bruijn_index=0),
            Token(de_bruijn_index=0),
        ]

        assert definition.kind == "function"
        assert definition.existence_uniqueness_proof_id is None


def test_register_explicit_function_rejects_duplicate_name() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        definitions = DefinitionService(session)

        x = register_term_var(symbols, "const_x_witness")
        body = formulas.register([Token(symbol_id=x.id)])
        first = definitions.register_explicit_function(
            name="const_x_like",
            param_symbol_ids=(),
            body_term_formula_id=body.id,
        )
        assert first.kind == "function"
        assert first.existence_uniqueness_proof_id is None

        with pytest.raises(Exception):
            definitions.register_explicit_function(
                name="const_x_like",
                param_symbol_ids=(),
                body_term_formula_id=body.id,
            )


def test_function_desc_rejects_unverified_existence_uniqueness_proof() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        definitions = DefinitionService(session)
        theorems = TheoremService(session)
        proofs = ProofService(session)

        value = register_term_var(symbols, "y_scratch")
        witness = register_term_var(symbols, "z_scratch")
        x = register_term_var(symbols, "x_target")
        eq = symbols.get_by_role("equality")

        phi = formulas.register(
            [Token(symbol_id=eq.id), Token(symbol_id=value.id), Token(symbol_id=x.id)]
        )
        statement_tokens = definitions.compute_existence_uniqueness_statement_tokens(
            (), value.id, witness.id, phi.id
        )
        statement = formulas.register(statement_tokens)
        theorem = theorems.register(name="unverified existence-uniqueness", conclusion_formula_id=statement.id)
        draft_proof = proofs.create_proof(theorem.id)
        # No steps added -> draft, never validated -> status stays "draft".

        with pytest.raises(ValidationError, match="must be verified"):
            definitions.register(
                DescriptiveFunctionDefinitionInput(
                    name="bad_function_desc",
                    param_symbol_ids=(),
                    value_symbol_id=value.id,
                    uniqueness_witness_symbol_id=witness.id,
                    body_formula_id=phi.id,
                    existence_uniqueness_proof_id=draft_proof.id,
                )
            )


def test_function_desc_rejects_existence_uniqueness_proof_with_premises() -> None:
    """Conservativity requires the existence-uniqueness statement to hold
    unconditionally. A theorem that only proves it *given a premise* (even a
    trivially self-entailing one, as built here) must be rejected."""
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        definitions = DefinitionService(session)
        theorems = TheoremService(session)
        proofs = ProofService(session)

        value = register_term_var(symbols, "y_premised")
        witness = register_term_var(symbols, "z_premised")
        x = register_term_var(symbols, "x_premised")
        eq = symbols.get_by_role("equality")

        phi = formulas.register(
            [Token(symbol_id=eq.id), Token(symbol_id=value.id), Token(symbol_id=x.id)]
        )
        statement_tokens = definitions.compute_existence_uniqueness_statement_tokens(
            (), value.id, witness.id, phi.id
        )
        statement = formulas.register(statement_tokens)

        theorem = theorems.register(
            name="premised existence-uniqueness",
            conclusion_formula_id=statement.id,
            premise_formula_ids=[statement.id],
        )
        proof = proofs.create_proof(theorem.id)
        proofs.add_step(proof.id, PremiseStepInput(0), statement.id)
        proofs.validate(proof.id)
        assert proofs.get(proof.id).status == "verified"

        with pytest.raises(ValidationError, match="no premises"):
            definitions.register(
                DescriptiveFunctionDefinitionInput(
                    name="bad_premised_function_desc",
                    param_symbol_ids=(),
                    value_symbol_id=value.id,
                    uniqueness_witness_symbol_id=witness.id,
                    body_formula_id=phi.id,
                    existence_uniqueness_proof_id=proof.id,
                )
            )
