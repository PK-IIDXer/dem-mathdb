from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dem.db.models import Base
from dem.db.seed import seed_inference_rules, seed_language
from dem.db.seeds.hilbert import seed_hilbert_core
from dem.errors import ConflictError, ValidationError
from dem.services.axiom import AxiomService
from dem.services.definition import DefinitionService
from dem.services.formula import FormulaService
from dem.services.proof import ProofService
from dem.services.symbol import SymbolService
from dem.types import (
    LogicalDefinitionInput,
    PredicateDefinitionInput,
    QuantPropDefinitionInput,
    QuantTermDefinitionInput,
    PropSubst,
    Substitution,
    SymbolTypeName,
    Token,
)


def make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_language(session)
    return session


def make_full_session() -> Session:
    """A session containing the full inference/lemma seed."""
    session = make_session()
    seed_inference_rules(session)
    seed_hilbert_core(session)
    return session


def register_prop_var(symbols: SymbolService, name: str, arity: int = 0):
    prop_type = symbols.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value)
    return symbols.register(name, prop_type.id, arity)


def register_term_var(symbols: SymbolService, name: str):
    term_type = symbols.get_symbol_type_by_name(SymbolTypeName.FREE_TERM_VAR.value)
    return symbols.register(name, term_type.id, 0)


def formula_tokens(formulas: FormulaService, formula_id: int) -> list[Token]:
    return [
        Token(symbol_id=row.symbol_id)
        if row.symbol_id is not None
        else Token(de_bruijn_index=row.de_bruijn_index)
        for row in formulas.get_tokens(formula_id)
    ]


def test_logical_definition_registers_symbol_axiom_and_params() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        definitions = DefinitionService(session)

        implication = symbols.get_by_role("implication")
        biconditional = symbols.get_by_role("biconditional")
        phi = register_prop_var(symbols, "Phi")
        psi = register_prop_var(symbols, "Psi")
        body = formulas.register(
            [Token(symbol_id=implication.id), Token(symbol_id=phi.id), Token(symbol_id=psi.id)]
        )

        definition = definitions.register(
            LogicalDefinitionInput(
                name="if_like",
                param_symbol_ids=(phi.id, psi.id),
                body_formula_id=body.id,
            )
        )

        new_symbol = definitions.get_symbol(definition.id)
        axiom = definitions.get_axiom(definition.id)

        assert definition.kind == "logical"
        assert new_symbol.name == "if_like"
        assert new_symbol.latex_template is None
        assert new_symbol.symbol_type.name == SymbolTypeName.LOGICAL.value
        assert new_symbol.arity == 2
        assert axiom.origin_kind == "definition_derived"
        assert axiom.definition_id == definition.id
        assert [symbol.id for symbol in definitions.list_formal_params(definition.id)] == [
            phi.id,
            psi.id,
        ]
        assert definitions.get_by_name("if_like").id == definition.id
        assert "if_like" in [row.name for row in definitions.list_all()]
        assert formula_tokens(formulas, axiom.formula_id) == [
            Token(symbol_id=biconditional.id),
            Token(symbol_id=new_symbol.id),
            Token(symbol_id=phi.id),
            Token(symbol_id=psi.id),
            Token(symbol_id=implication.id),
            Token(symbol_id=phi.id),
            Token(symbol_id=psi.id),
        ]


def test_definition_registration_normalizes_and_stores_latex_template() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        definitions = DefinitionService(session)

        phi = register_prop_var(symbols, "TemplatePhi")
        body = formulas.register([Token(symbol_id=phi.id)])
        definition = definitions.register(
            LogicalDefinitionInput(
                name="TemplateLogical",
                param_symbol_ids=(phi.id,),
                body_formula_id=body.id,
                latex_template=r"  \mathsf{TemplateLogical}  ",
            )
        )

        assert definitions.get_symbol(definition.id).latex_template == r"\mathsf{TemplateLogical}"


def test_whitespace_definition_template_keeps_the_name_fallback() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        definitions = DefinitionService(session)

        phi = register_prop_var(symbols, "FallbackPhi")
        body = formulas.register([Token(symbol_id=phi.id)])
        definition = definitions.register(
            LogicalDefinitionInput(
                name="FallbackLogical",
                param_symbol_ids=(phi.id,),
                body_formula_id=body.id,
                latex_template="   ",
            )
        )

        assert definitions.get_symbol(definition.id).latex_template is None


def test_register_explicit_function_uses_equality_as_defining_axiom() -> None:
    with make_full_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        definitions = DefinitionService(session)

        equality = symbols.get_by_role("equality")
        witness = register_term_var(symbols, "E")
        body = formulas.register([Token(symbol_id=witness.id)])

        definition = definitions.register_explicit_function(
            name="empty_like",
            param_symbol_ids=(),
            body_term_formula_id=body.id,
        )

        new_symbol = definitions.get_symbol(definition.id)
        axiom = definitions.get_axiom(definition.id)

        assert definition.kind == "function"
        assert definition.requires_existence_proof is False
        assert definition.requires_uniqueness_proof is False
        assert definition.existence_uniqueness_proof_id is None
        assert new_symbol.symbol_type.name == SymbolTypeName.FUNCTION.value
        assert new_symbol.arity == 0
        assert definitions.list_formal_params(definition.id) == []
        assert definition.display_formula is not None
        # The readable formula and the proof-facing defining axiom are the
        # same direct equality: empty_like = E.
        assert formula_tokens(formulas, definition.display_formula.id) == [
            Token(symbol_id=equality.id),
            Token(symbol_id=new_symbol.id),
            Token(symbol_id=witness.id),
        ]
        assert formula_tokens(formulas, axiom.formula_id) == [
            Token(symbol_id=equality.id),
            Token(symbol_id=new_symbol.id),
            Token(symbol_id=witness.id),
        ]
        assert definition.display_formula_id == axiom.formula_id


def test_predicate_definition_abstracts_term_params_with_outer_foralls() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        definitions = DefinitionService(session)

        forall = symbols.get_by_role("universal_quantifier")
        implication = symbols.get_by_role("implication")
        biconditional = symbols.get_by_role("biconditional")
        equality = symbols.get_by_role("equality")
        left = register_term_var(symbols, "A")
        right = register_term_var(symbols, "B")
        body = formulas.register(
            [
                Token(symbol_id=forall.id),
                Token(symbol_id=implication.id),
                Token(symbol_id=equality.id),
                Token(de_bruijn_index=0),
                Token(symbol_id=left.id),
                Token(symbol_id=equality.id),
                Token(de_bruijn_index=0),
                Token(symbol_id=right.id),
            ]
        )

        definition = definitions.register(
            PredicateDefinitionInput(
                name="rel_like",
                param_symbol_ids=(left.id, right.id),
                body_formula_id=body.id,
            )
        )

        new_symbol = definitions.get_symbol(definition.id)
        axiom = definitions.get_axiom(definition.id)

        assert new_symbol.symbol_type.name == SymbolTypeName.PREDICATE.value
        assert formula_tokens(formulas, axiom.formula_id) == [
            Token(symbol_id=forall.id),
            Token(symbol_id=forall.id),
            Token(symbol_id=biconditional.id),
            Token(symbol_id=new_symbol.id),
            Token(de_bruijn_index=1),
            Token(de_bruijn_index=0),
            Token(symbol_id=forall.id),
            Token(symbol_id=implication.id),
            Token(symbol_id=equality.id),
            Token(de_bruijn_index=0),
            Token(de_bruijn_index=2),
            Token(symbol_id=equality.id),
            Token(de_bruijn_index=0),
            Token(de_bruijn_index=1),
        ]


def test_quant_prop_definition_uses_bound_argument_on_lhs_only() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        definitions = DefinitionService(session)

        biconditional = symbols.get_by_role("biconditional")
        phi = register_prop_var(symbols, "Phi1", arity=1)
        x = register_term_var(symbols, "x")
        body = formulas.register([Token(symbol_id=phi.id), Token(symbol_id=x.id)])

        definition = definitions.register(
            QuantPropDefinitionInput(
                name="exists_one_like",
                param_symbol_id=phi.id,
                body_formula_id=body.id,
            )
        )

        new_symbol = definitions.get_symbol(definition.id)
        axiom = definitions.get_axiom(definition.id)

        assert new_symbol.symbol_type.name == SymbolTypeName.QUANT_PROP.value
        assert new_symbol.arity == 1
        assert [symbol.id for symbol in definitions.list_formal_params(definition.id)] == [phi.id]
        assert formula_tokens(formulas, axiom.formula_id) == [
            Token(symbol_id=biconditional.id),
            Token(symbol_id=new_symbol.id),
            Token(symbol_id=phi.id),
            Token(de_bruijn_index=0),
            Token(symbol_id=phi.id),
            Token(symbol_id=x.id),
        ]


def test_quant_prop_substitution_shifts_the_same_schema_at_nested_depths() -> None:
    """A formal schema may occur below different binders, as in ``∃!``."""
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        definitions = DefinitionService(session)
        proofs = ProofService(session)

        biconditional = symbols.get_by_role("biconditional")
        forall = symbols.get_by_role("universal_quantifier")
        exists = symbols.get_by_name("∃")
        conjunction = symbols.get_by_name("∧")
        implication = symbols.get_by_role("implication")
        equality = symbols.get_by_role("equality")
        phi = register_prop_var(symbols, "NestedPhi1", arity=1)
        schema_param = register_term_var(symbols, "schema_x")

        # ∃x (φ(x) ∧ ∀y (φ(y) → y=x)): φ occurs at depths one and two.
        body = formulas.register(
            [
                Token(symbol_id=exists.id),
                Token(symbol_id=conjunction.id),
                Token(symbol_id=phi.id),
                Token(de_bruijn_index=0),
                Token(symbol_id=forall.id),
                Token(symbol_id=implication.id),
                Token(symbol_id=phi.id),
                Token(de_bruijn_index=0),
                Token(symbol_id=equality.id),
                Token(de_bruijn_index=0),
                Token(de_bruijn_index=1),
            ]
        )
        definition = definitions.register(
            QuantPropDefinitionInput(
                name="nested_exists_unique_like",
                param_symbol_id=phi.id,
                body_formula_id=body.id,
            )
        )

        # λz. ∀w(z=w) has a binder of its own.  In every occurrence z must be
        # shifted past that local binder instead of being captured by w.
        schema = formulas.register(
            [
                Token(symbol_id=forall.id),
                Token(symbol_id=equality.id),
                Token(symbol_id=schema_param.id),
                Token(de_bruijn_index=0),
            ]
        )
        instantiated = proofs.compute_substituted_tokens(
            definitions.get_axiom(definition.id).formula_id,
            Substitution(
                prop_substs=(
                    PropSubst(phi.id, schema.id, (schema_param.id,)),
                )
            ),
        )
        new_symbol = definition.new_symbol
        schema_at_bound = [
            Token(symbol_id=forall.id),
            Token(symbol_id=equality.id),
            Token(de_bruijn_index=1),
            Token(de_bruijn_index=0),
        ]
        assert instantiated == [
            Token(symbol_id=biconditional.id),
            Token(symbol_id=new_symbol.id),
            *schema_at_bound,
            Token(symbol_id=exists.id),
            Token(symbol_id=conjunction.id),
            *schema_at_bound,
            Token(symbol_id=forall.id),
            Token(symbol_id=implication.id),
            *schema_at_bound,
            Token(symbol_id=equality.id),
            Token(de_bruijn_index=0),
            Token(de_bruijn_index=1),
        ]


def register_term_binder(symbols: SymbolService, name: str):
    """Register a generic primitive term binder for a service-level test."""
    quant_term = symbols.get_symbol_type_by_name(SymbolTypeName.QUANT_TERM.value)
    return symbols.register(name, quant_term.id, 1)


def test_quant_term_definition_uses_equality_and_bound_argument_on_lhs() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        definitions = DefinitionService(session)

        equality = symbols.get_by_role("equality")
        conjunction = symbols.get_by_name("∧")
        chooser = register_term_binder(symbols, "Choose")
        guard = symbols.register(
            "Guard",
            symbols.get_symbol_type_by_name(SymbolTypeName.PREDICATE.value).id,
            1,
        )
        phi = register_prop_var(symbols, "Phi1", arity=1)

        # body := Choose x. (Guard(x) and phi(x)).
        body = formulas.register(
            [
                Token(symbol_id=chooser.id),
                Token(symbol_id=conjunction.id),
                Token(symbol_id=guard.id),
                Token(de_bruijn_index=0),
                Token(symbol_id=phi.id),
                Token(de_bruijn_index=0),
            ]
        )

        definition = definitions.register(
            QuantTermDefinitionInput(
            name="Choose_guarded",
                param_symbol_id=phi.id,
                body_formula_id=body.id,
            )
        )

        new_symbol = definitions.get_symbol(definition.id)
        axiom = definitions.get_axiom(definition.id)

        assert definition.kind == "quant_term"
        assert new_symbol.symbol_type.name == SymbolTypeName.QUANT_TERM.value
        assert new_symbol.arity == 1
        assert new_symbol.is_primitive is False
        assert [symbol.id for symbol in definitions.list_formal_params(definition.id)] == [phi.id]
        # The defining axiom is an equation, not a biconditional: the definiendum
        # is a term. Its right-hand side keeps the body's own binder depth, since
        # the body brings its own binder rather than borrowing the new symbol's.
        assert formula_tokens(formulas, axiom.formula_id) == [
            Token(symbol_id=equality.id),
            Token(symbol_id=new_symbol.id),
            Token(symbol_id=phi.id),
            Token(de_bruijn_index=0),
            *formula_tokens(formulas, body.id),
        ]
        assert axiom.origin_kind == "definition_derived"
        assert axiom.definition_id == definition.id
        # Explicit abbreviation: conservative on its own, so no existence or
        # uniqueness homework is claimed. A DEM term is well-formed whether or not
        # it denotes, so `N = B` says nothing about `Guard(N x. phi(x))` -- that
        # would need a separate theorem. See docs/design/kernel/definition.md.
        assert definition.requires_existence_proof is False
        assert definition.requires_uniqueness_proof is False
        assert definition.existence_uniqueness_proof_id is None
        # ... and exactly one axiom came out of the registration.
        assert [row.id for row in AxiomService(session).list_axioms()] == [axiom.id]


def test_quant_term_definition_rejects_bad_param_and_body_shapes() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        definitions = DefinitionService(session)

        phi0 = register_prop_var(symbols, "Phi0")
        phi1 = register_prop_var(symbols, "Phi1", arity=1)
        x = register_term_var(symbols, "x")
        prop_body = formulas.register([Token(symbol_id=phi0.id)])
        term_body = formulas.register([Token(symbol_id=x.id)])

        with pytest.raises(ValidationError, match="quant_term definition body must be"):
            definitions.register(
                QuantTermDefinitionInput(
                    name="bad_quant_term_body",
                    param_symbol_id=phi1.id,
                    body_formula_id=prop_body.id,
                )
            )

        with pytest.raises(ValidationError, match="quantifier definition parameter"):
            definitions.register(
                QuantTermDefinitionInput(
                    name="bad_quant_term_param",
                    param_symbol_id=phi0.id,
                    body_formula_id=term_body.id,
                )
            )


def test_definition_input_validation_rejects_bad_param_and_body_shapes() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        definitions = DefinitionService(session)

        phi0 = register_prop_var(symbols, "Phi0")
        phi1 = register_prop_var(symbols, "BadPhi1", arity=1)
        phi2 = register_prop_var(symbols, "BadPhi2", arity=2)
        term = register_term_var(symbols, "t")
        prop_body = formulas.register([Token(symbol_id=phi0.id)])

        with pytest.raises(ValidationError, match="logical definition parameters"):
            definitions.register(
                LogicalDefinitionInput(
                    name="bad_logical",
                    param_symbol_ids=(phi1.id,),
                    body_formula_id=prop_body.id,
                )
            )

        with pytest.raises(ValidationError, match="predicate/function definition parameters"):
            definitions.register(
                PredicateDefinitionInput(
                    name="bad_predicate",
                    param_symbol_ids=(phi0.id,),
                    body_formula_id=prop_body.id,
                )
            )

        with pytest.raises(ValidationError, match="function definition body must be"):
            definitions.register_explicit_function(
                name="bad_function",
                param_symbol_ids=(),
                body_term_formula_id=prop_body.id,
            )

        with pytest.raises(ValidationError, match="quantifier definition parameter"):
            definitions.register(
                QuantPropDefinitionInput(
                    name="bad_quant",
                    param_symbol_id=phi0.id,
                    body_formula_id=prop_body.id,
                )
            )

        # arity >= 2 must be rejected too: compute_defining_formula_tokens only ever
        # supplies a single bound-variable argument for the formal parameter, so an
        # arity-2 formal parameter would otherwise crash downstream in FormulaService
        # (or worse, silently misparse the body) instead of failing validation cleanly.
        with pytest.raises(ValidationError, match="quantifier definition parameter"):
            definitions.register(
                QuantPropDefinitionInput(
                    name="bad_quant_arity_two",
                    param_symbol_id=phi2.id,
                    body_formula_id=prop_body.id,
                )
            )

        with pytest.raises(ValidationError, match="definition formal parameters"):
            definitions.register(
                PredicateDefinitionInput(
                    name="bad_duplicate_params",
                    param_symbol_ids=(term.id, term.id),
                    body_formula_id=prop_body.id,
                )
            )


def test_register_rejects_name_colliding_with_existing_symbol() -> None:
    """A definition must not silently reuse an already-meaningful symbol
    name -- that would make the new defining axiom ambiguous with whatever
    the old symbol meant, breaking conservativity."""
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        definitions = DefinitionService(session)

        phi = register_prop_var(symbols, "CollidePhi")
        psi = register_prop_var(symbols, "CollidePsi")
        implication = symbols.get_by_role("implication")
        body = formulas.register(
            [Token(symbol_id=implication.id), Token(symbol_id=phi.id), Token(symbol_id=psi.id)]
        )

        with pytest.raises(ConflictError, match="Symbol"):
            definitions.register(
                LogicalDefinitionInput(
                    name="∧",  # already a primitive symbol from seed_language
                    param_symbol_ids=(phi.id, psi.id),
                    body_formula_id=body.id,
                )
            )


def test_register_rejects_name_colliding_with_existing_axiom() -> None:
    """Same guard, for the derived "<name> 定義公理" axiom name: even if no
    Symbol or Definition named `shadow_target` exists yet, a pre-existing
    axiom occupying that derived name must still block registration."""
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        definitions = DefinitionService(session)
        axioms = AxiomService(session)

        phi = register_prop_var(symbols, "AxCollidePhi")
        psi = register_prop_var(symbols, "AxCollidePsi")
        implication = symbols.get_by_role("implication")
        body = formulas.register(
            [Token(symbol_id=implication.id), Token(symbol_id=phi.id), Token(symbol_id=psi.id)]
        )
        axioms.register(name="shadow_target 定義公理", formula_id=body.id)

        with pytest.raises(ConflictError, match="Axiom"):
            definitions.register(
                LogicalDefinitionInput(
                    name="shadow_target",
                    param_symbol_ids=(phi.id, psi.id),
                    body_formula_id=body.id,
                )
            )
