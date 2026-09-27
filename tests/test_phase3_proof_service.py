from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dem.db.models import Base
from dem.db.seed import seed_inference_rules, seed_language
from dem.errors import ProofValidationError, ValidationError
from dem.identity import deterministic_public_id
from dem.services.axiom import AxiomService
from dem.services.formula import FormulaService
from dem.services.proof import (
    ProofService,
    abstract_and_quantify_pure,
    apply_substitution_pure,
)
from dem.services.symbol import SymbolService
from dem.services.theorem import TheoremService
from dem.types import (
    AssumptionStepInput,
    AxiomStepInput,
    FormulaTypeName,
    GenStepInput,
    MPStepInput,
    PremiseStepInput,
    PropSubst,
    Substitution,
    SymbolMeta,
    SymbolTypeName,
    TheoremStepInput,
    Token,
)


def make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_language(session)
    seed_inference_rules(session)
    return session


def register_prop_var(symbols: SymbolService, name: str, arity: int = 0):
    prop_type = symbols.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value)
    return symbols.register(name, prop_type.id, arity)


def register_term_var(symbols: SymbolService, name: str):
    term_type = symbols.get_symbol_type_by_name(SymbolTypeName.FREE_TERM_VAR.value)
    return symbols.register(name, term_type.id, 0)


def test_proof_identity_ordinal_is_not_reused_after_deletion() -> None:
    session = make_session()
    try:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        theorems = TheoremService(session)
        proofs = ProofService(session)
        proposition = register_prop_var(symbols, "proof_identity_prop")
        formula = formulas.register([Token(symbol_id=proposition.id)])
        theorem = theorems.register("proof identity theorem", formula.id)
        first = proofs.create_proof(theorem.id)
        second = proofs.create_proof(theorem.id)
        assert (first.identity_ordinal, second.identity_ordinal) == (0, 1)

        session.delete(first)
        session.flush()
        third = proofs.create_proof(theorem.id)

        assert third.identity_ordinal == 2
        assert third.public_id == deterministic_public_id(
            "proof", f"{theorem.public_id}::2"
        )
        assert third.public_id != second.public_id
    finally:
        session.close()


def test_pure_term_substitution_is_simultaneous() -> None:
    meta = {
        1: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
        2: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
        3: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
    }

    result = apply_substitution_pure(
        [Token(symbol_id=1)],
        prop_subst={},
        term_subst={1: [Token(symbol_id=2)], 2: [Token(symbol_id=3)]},
        symbol_meta=meta,
    )

    assert result == [Token(symbol_id=2)]


def test_abstract_and_quantify_does_not_shift_existing_bound_indices() -> None:
    meta = {
        1: SymbolMeta(1, SymbolTypeName.QUANT_PROP, FormulaTypeName.PROPOSITION, FormulaTypeName.PROPOSITION, True),
        2: SymbolMeta(1, SymbolTypeName.FREE_PROP_VAR, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        3: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
    }

    result = abstract_and_quantify_pure(
        [Token(symbol_id=1), Token(symbol_id=2), Token(de_bruijn_index=0)],
        variable_symbol_id=3,
        forall_symbol_id=1,
        symbol_meta=meta,
    )

    assert result == [
        Token(symbol_id=1),
        Token(symbol_id=1),
        Token(symbol_id=2),
        Token(de_bruijn_index=0),
    ]


# -- apply_substitution_pure: capture avoidance / simultaneity property tests --
#
# See docs/design/kernel/trust-boundary.md §8 item 1.


def test_pure_term_substitution_swap_is_simultaneous_not_sequential() -> None:
    """{a: b, b: a} applied to P(a, b) must swap to P(b, a), not P(a, a) or
    P(b, b) -- a sequential (non-simultaneous) implementation would corrupt
    this because the output of substituting `a` would itself be re-scanned
    for `b`, or vice versa."""
    meta = {
        1: SymbolMeta(2, SymbolTypeName.PREDICATE, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        2: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
        3: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
    }

    result = apply_substitution_pure(
        [Token(symbol_id=1), Token(symbol_id=2), Token(symbol_id=3)],
        prop_subst={},
        term_subst={2: [Token(symbol_id=3)], 3: [Token(symbol_id=2)]},
        symbol_meta=meta,
    )

    assert result == [Token(symbol_id=1), Token(symbol_id=3), Token(symbol_id=2)]


def test_pure_term_substitution_shifts_bound_target_under_quantifier() -> None:
    """A term_subst target that itself carries a dangling bound-variable token
    (never produced by a registered, closed Formula, but exercised here to
    pin the shift mechanism `_replace_term_vars`/`_shift_free_de_bruijn` in
    isolation) must be shifted by the number of quantifiers crossed while
    descending to the substitution site, so the reference still lands on
    whatever binder it originally pointed to."""
    meta = {
        1: SymbolMeta(1, SymbolTypeName.QUANT_PROP, FormulaTypeName.PROPOSITION, FormulaTypeName.PROPOSITION, True),
        2: SymbolMeta(1, SymbolTypeName.PREDICATE, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        3: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
    }

    # ∀ (Q(w)), substituting w := bound(0) (referring to whatever this
    # dangling index means from outside) should yield ∀ (Q(bound(1))).
    result = apply_substitution_pure(
        [Token(symbol_id=1), Token(symbol_id=2), Token(symbol_id=3)],
        prop_subst={},
        term_subst={3: [Token(de_bruijn_index=0)]},
        symbol_meta=meta,
    )

    assert result == [Token(symbol_id=1), Token(symbol_id=2), Token(de_bruijn_index=1)]


def test_pure_prop_var_substitution_applies_formal_param_without_quantifier() -> None:
    """Baseline (no binder crossing): phi1(a) with body P(param) instantiates
    to P(a) directly."""
    meta = {
        2: SymbolMeta(1, SymbolTypeName.FREE_PROP_VAR, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        4: SymbolMeta(1, SymbolTypeName.PREDICATE, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        5: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
        6: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
    }

    result = apply_substitution_pure(
        [Token(symbol_id=2), Token(symbol_id=5)],
        prop_subst={2: ([Token(symbol_id=4), Token(symbol_id=6)], (6,))},
        term_subst={},
        symbol_meta=meta,
    )

    assert result == [Token(symbol_id=4), Token(symbol_id=5)]


def test_pure_prop_var_substitution_applies_a_compound_term_argument() -> None:
    meta = {
        2: SymbolMeta(1, SymbolTypeName.FREE_PROP_VAR, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        4: SymbolMeta(1, SymbolTypeName.PREDICATE, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        5: SymbolMeta(1, SymbolTypeName.FUNCTION, FormulaTypeName.TERM, FormulaTypeName.TERM, False),
        6: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
        7: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
    }

    result = apply_substitution_pure(
        [Token(symbol_id=2), Token(symbol_id=5), Token(symbol_id=6)],
        prop_subst={2: ([Token(symbol_id=4), Token(symbol_id=7)], (7,))},
        term_subst={},
        symbol_meta=meta,
    )

    assert result == [Token(symbol_id=4), Token(symbol_id=5), Token(symbol_id=6)]


def test_pure_prop_var_substitution_preserves_compound_argument_boundaries() -> None:
    meta = {
        2: SymbolMeta(2, SymbolTypeName.FREE_PROP_VAR, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        4: SymbolMeta(2, SymbolTypeName.PREDICATE, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        5: SymbolMeta(1, SymbolTypeName.FUNCTION, FormulaTypeName.TERM, FormulaTypeName.TERM, False),
        6: SymbolMeta(2, SymbolTypeName.FUNCTION, FormulaTypeName.TERM, FormulaTypeName.TERM, False),
        7: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
        8: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
        9: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
        10: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
    }

    result = apply_substitution_pure(
        [
            Token(symbol_id=2),
            Token(symbol_id=5),
            Token(symbol_id=7),
            Token(symbol_id=6),
            Token(symbol_id=8),
            Token(symbol_id=9),
        ],
        prop_subst={
            2: (
                [Token(symbol_id=4), Token(symbol_id=10), Token(symbol_id=9)],
                (10, 9),
            )
        },
        term_subst={},
        symbol_meta=meta,
    )

    assert result == [
        Token(symbol_id=4),
        Token(symbol_id=5),
        Token(symbol_id=7),
        Token(symbol_id=6),
        Token(symbol_id=8),
        Token(symbol_id=9),
    ]


def test_pure_prop_var_substitution_recurses_into_original_term_argument() -> None:
    meta = {
        2: SymbolMeta(1, SymbolTypeName.FREE_PROP_VAR, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        3: SymbolMeta(1, SymbolTypeName.FREE_PROP_VAR, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        4: SymbolMeta(1, SymbolTypeName.QUANT_TERM, FormulaTypeName.TERM, FormulaTypeName.PROPOSITION, True),
        5: SymbolMeta(1, SymbolTypeName.PREDICATE, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        6: SymbolMeta(1, SymbolTypeName.PREDICATE, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        7: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
        8: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
    }

    result = apply_substitution_pure(
        [
            Token(symbol_id=2),
            Token(symbol_id=4),
            Token(symbol_id=3),
            Token(de_bruijn_index=0),
        ],
        prop_subst={
            2: ([Token(symbol_id=5), Token(symbol_id=7)], (7,)),
            3: ([Token(symbol_id=6), Token(symbol_id=8)], (8,)),
        },
        term_subst={},
        symbol_meta=meta,
    )

    assert result == [
        Token(symbol_id=5),
        Token(symbol_id=4),
        Token(symbol_id=6),
        Token(de_bruijn_index=0),
    ]


def test_pure_prop_var_substitution_of_a_self_nested_argument_terminates() -> None:
    meta = {
        2: SymbolMeta(1, SymbolTypeName.FREE_PROP_VAR, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        4: SymbolMeta(1, SymbolTypeName.QUANT_TERM, FormulaTypeName.TERM, FormulaTypeName.PROPOSITION, True),
        5: SymbolMeta(1, SymbolTypeName.PREDICATE, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        6: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
    }

    result = apply_substitution_pure(
        [
            Token(symbol_id=2),
            Token(symbol_id=4),
            Token(symbol_id=2),
            Token(de_bruijn_index=0),
        ],
        prop_subst={2: ([Token(symbol_id=5), Token(symbol_id=6)], (6,))},
        term_subst={},
        symbol_meta=meta,
    )

    assert result == [
        Token(symbol_id=5),
        Token(symbol_id=4),
        Token(symbol_id=5),
        Token(de_bruijn_index=0),
    ]


def test_pure_prop_var_substitution_does_not_rescan_inserted_body() -> None:
    meta = {
        2: SymbolMeta(1, SymbolTypeName.FREE_PROP_VAR, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        3: SymbolMeta(1, SymbolTypeName.FREE_PROP_VAR, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        4: SymbolMeta(1, SymbolTypeName.PREDICATE, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        5: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
        6: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
        7: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
    }

    result = apply_substitution_pure(
        [Token(symbol_id=2), Token(symbol_id=5)],
        prop_subst={
            2: ([Token(symbol_id=3), Token(symbol_id=6)], (6,)),
            3: ([Token(symbol_id=4), Token(symbol_id=7)], (7,)),
        },
        term_subst={},
        symbol_meta=meta,
    )

    assert result == [Token(symbol_id=3), Token(symbol_id=5)]


def test_pure_prop_var_substitution_shifts_a_compound_bound_argument() -> None:
    meta = {
        1: SymbolMeta(1, SymbolTypeName.QUANT_PROP, FormulaTypeName.PROPOSITION, FormulaTypeName.PROPOSITION, True),
        2: SymbolMeta(1, SymbolTypeName.FREE_PROP_VAR, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        3: SymbolMeta(1, SymbolTypeName.QUANT_PROP, FormulaTypeName.PROPOSITION, FormulaTypeName.PROPOSITION, True),
        4: SymbolMeta(1, SymbolTypeName.PREDICATE, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        5: SymbolMeta(1, SymbolTypeName.FUNCTION, FormulaTypeName.TERM, FormulaTypeName.TERM, False),
        6: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
    }

    result = apply_substitution_pure(
        [
            Token(symbol_id=1),
            Token(symbol_id=2),
            Token(symbol_id=5),
            Token(de_bruijn_index=0),
        ],
        prop_subst={
            2: (
                [Token(symbol_id=3), Token(symbol_id=4), Token(symbol_id=6)],
                (6,),
            )
        },
        term_subst={},
        symbol_meta=meta,
    )

    assert result == [
        Token(symbol_id=1),
        Token(symbol_id=3),
        Token(symbol_id=4),
        Token(symbol_id=5),
        Token(de_bruijn_index=1),
    ]


def test_pure_prop_var_substitution_shift_respects_binders_inside_argument() -> None:
    meta = {
        1: SymbolMeta(1, SymbolTypeName.QUANT_PROP, FormulaTypeName.PROPOSITION, FormulaTypeName.PROPOSITION, True),
        2: SymbolMeta(1, SymbolTypeName.FREE_PROP_VAR, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        3: SymbolMeta(1, SymbolTypeName.QUANT_PROP, FormulaTypeName.PROPOSITION, FormulaTypeName.PROPOSITION, True),
        4: SymbolMeta(1, SymbolTypeName.QUANT_TERM, FormulaTypeName.TERM, FormulaTypeName.PROPOSITION, True),
        5: SymbolMeta(1, SymbolTypeName.PREDICATE, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        6: SymbolMeta(2, SymbolTypeName.PREDICATE, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        7: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
    }

    result = apply_substitution_pure(
        [
            Token(symbol_id=1),
            Token(symbol_id=2),
            Token(symbol_id=4),
            Token(symbol_id=6),
            Token(de_bruijn_index=1),
            Token(de_bruijn_index=0),
        ],
        prop_subst={
            2: (
                [Token(symbol_id=3), Token(symbol_id=5), Token(symbol_id=7)],
                (7,),
            )
        },
        term_subst={},
        symbol_meta=meta,
    )

    assert result == [
        Token(symbol_id=1),
        Token(symbol_id=3),
        Token(symbol_id=5),
        Token(symbol_id=4),
        Token(symbol_id=6),
        Token(de_bruijn_index=2),
        Token(de_bruijn_index=0),
    ]


def test_term_pass_applies_after_a_compound_argument_is_duplicated() -> None:
    meta = {
        2: SymbolMeta(1, SymbolTypeName.FREE_PROP_VAR, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        3: SymbolMeta(2, SymbolTypeName.PREDICATE, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        4: SymbolMeta(1, SymbolTypeName.FUNCTION, FormulaTypeName.TERM, FormulaTypeName.TERM, False),
        5: SymbolMeta(1, SymbolTypeName.FUNCTION, FormulaTypeName.TERM, FormulaTypeName.TERM, False),
        6: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
        7: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
        8: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
    }

    result = apply_substitution_pure(
        [Token(symbol_id=2), Token(symbol_id=4), Token(symbol_id=6)],
        prop_subst={
            2: (
                [Token(symbol_id=3), Token(symbol_id=7), Token(symbol_id=7)],
                (7,),
            )
        },
        term_subst={6: [Token(symbol_id=5), Token(symbol_id=8)]},
        symbol_meta=meta,
    )

    assert result == [
        Token(symbol_id=3),
        Token(symbol_id=4),
        Token(symbol_id=5),
        Token(symbol_id=8),
        Token(symbol_id=4),
        Token(symbol_id=5),
        Token(symbol_id=8),
    ]


def test_pure_prop_var_substitution_shifts_bound_argument_under_new_quantifier() -> None:
    """Capture avoidance: instantiating phi1(y) (y bound by an *outer*
    quantifier at the call site) with a body that introduces its *own* new
    quantifier before reaching the formal-param position must shift the
    argument's bound-variable reference so it still resolves to the outer
    binder, not the newly introduced one.

    forall y (phi1(y))   with phi1(p) := forall z (P(p))
      => forall y (forall z (P(y)))

    P(y) inside the inner binder needs de Bruijn index 1 (skip the fresh
    inner ∀, then hit the original outer ∀) -- not 0, which would mean "the
    inner ∀'s own variable" and would be a capture bug.
    """
    meta = {
        1: SymbolMeta(1, SymbolTypeName.QUANT_PROP, FormulaTypeName.PROPOSITION, FormulaTypeName.PROPOSITION, True),
        2: SymbolMeta(1, SymbolTypeName.FREE_PROP_VAR, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        3: SymbolMeta(1, SymbolTypeName.QUANT_PROP, FormulaTypeName.PROPOSITION, FormulaTypeName.PROPOSITION, True),
        4: SymbolMeta(1, SymbolTypeName.PREDICATE, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        6: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
    }

    outer = [Token(symbol_id=1), Token(symbol_id=2), Token(de_bruijn_index=0)]
    body = [Token(symbol_id=3), Token(symbol_id=4), Token(symbol_id=6)]

    result = apply_substitution_pure(
        outer,
        prop_subst={2: (body, (6,))},
        term_subst={},
        symbol_meta=meta,
    )

    assert result == [
        Token(symbol_id=1),
        Token(symbol_id=3),
        Token(symbol_id=4),
        Token(de_bruijn_index=1),
    ]


def test_pure_prop_var_substitution_shifts_across_two_new_quantifiers() -> None:
    """Same shape as above but the substituted body introduces two nested
    quantifiers before the formal-param position, so the shift must
    accumulate to 2, not saturate at 1."""
    meta = {
        1: SymbolMeta(1, SymbolTypeName.QUANT_PROP, FormulaTypeName.PROPOSITION, FormulaTypeName.PROPOSITION, True),
        2: SymbolMeta(1, SymbolTypeName.FREE_PROP_VAR, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        3: SymbolMeta(1, SymbolTypeName.QUANT_PROP, FormulaTypeName.PROPOSITION, FormulaTypeName.PROPOSITION, True),
        4: SymbolMeta(1, SymbolTypeName.PREDICATE, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        6: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
    }

    outer = [Token(symbol_id=1), Token(symbol_id=2), Token(de_bruijn_index=0)]
    # phi1(p) := forall z1 (forall z2 (P(p)))
    body = [Token(symbol_id=3), Token(symbol_id=3), Token(symbol_id=4), Token(symbol_id=6)]

    result = apply_substitution_pure(
        outer,
        prop_subst={2: (body, (6,))},
        term_subst={},
        symbol_meta=meta,
    )

    assert result == [
        Token(symbol_id=1),
        Token(symbol_id=3),
        Token(symbol_id=3),
        Token(symbol_id=4),
        Token(de_bruijn_index=2),
    ]


# -- abstract_and_quantify_pure: multi-occurrence / vacuous / malformed-input --
#
# See docs/design/kernel/trust-boundary.md §8 item 2.


def test_abstract_and_quantify_replaces_all_occurrences_at_their_own_depth() -> None:
    """Every free occurrence of the abstracted variable becomes a bound-var
    token whose index reflects *its own* nesting depth relative to the new
    outer quantifier, not a single shared index."""
    meta = {
        1: SymbolMeta(1, SymbolTypeName.QUANT_PROP, FormulaTypeName.PROPOSITION, FormulaTypeName.PROPOSITION, True),
        2: SymbolMeta(2, SymbolTypeName.LOGICAL, FormulaTypeName.PROPOSITION, FormulaTypeName.PROPOSITION, False),
        3: SymbolMeta(1, SymbolTypeName.PREDICATE, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        4: SymbolMeta(1, SymbolTypeName.QUANT_PROP, FormulaTypeName.PROPOSITION, FormulaTypeName.PROPOSITION, True),
        5: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
    }

    # AND(P(x), forall z (P(x)))
    body = [
        Token(symbol_id=2),
        Token(symbol_id=3),
        Token(symbol_id=5),
        Token(symbol_id=4),
        Token(symbol_id=3),
        Token(symbol_id=5),
    ]

    result = abstract_and_quantify_pure(
        body, variable_symbol_id=5, forall_symbol_id=1, symbol_meta=meta
    )

    assert result == [
        Token(symbol_id=1),
        Token(symbol_id=2),
        Token(symbol_id=3),
        Token(de_bruijn_index=0),
        Token(symbol_id=4),
        Token(symbol_id=3),
        Token(de_bruijn_index=1),
    ]


def test_abstract_and_quantify_is_vacuous_when_variable_does_not_occur() -> None:
    """Generalizing over a variable that is not free in the body is a
    degenerate but valid Hilbert-style Gen: the body is wrapped unchanged."""
    meta = {
        1: SymbolMeta(1, SymbolTypeName.QUANT_PROP, FormulaTypeName.PROPOSITION, FormulaTypeName.PROPOSITION, True),
        3: SymbolMeta(0, SymbolTypeName.PREDICATE, FormulaTypeName.PROPOSITION, None, False),
        5: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
    }

    result = abstract_and_quantify_pure(
        [Token(symbol_id=3)], variable_symbol_id=5, forall_symbol_id=1, symbol_meta=meta
    )

    assert result == [Token(symbol_id=1), Token(symbol_id=3)]


def test_abstract_and_quantify_rejects_malformed_token_sequence() -> None:
    """A truncated token list (missing an expected argument) must raise
    rather than silently return a mismatched abstraction."""
    meta = {
        1: SymbolMeta(1, SymbolTypeName.QUANT_PROP, FormulaTypeName.PROPOSITION, FormulaTypeName.PROPOSITION, True),
        3: SymbolMeta(1, SymbolTypeName.PREDICATE, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, False),
        5: SymbolMeta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, False),
    }

    with pytest.raises(ValidationError):
        # P(...) declares arity 1 but has no argument token.
        abstract_and_quantify_pure(
            [Token(symbol_id=3)], variable_symbol_id=5, forall_symbol_id=1, symbol_meta=meta
        )


def test_premise_proof_validates_and_promotes_theorem() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        theorems = TheoremService(session)
        proofs = ProofService(session)

        phi = register_prop_var(symbols, "φ")
        phi_formula = formulas.register([Token(symbol_id=phi.id)])
        theorem = theorems.register("phi_from_phi", phi_formula.id, [phi_formula.id])
        proof = proofs.create_proof(theorem.id)

        proofs.add_step(proof.id, PremiseStepInput(0), phi_formula.id)
        proofs.validate(proof.id)

        assert proofs.get(proof.id).status == "verified"
        assert theorems.get(theorem.id).status == "proven"


def test_generalization_validates_when_variable_not_free_in_premises() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        axioms = AxiomService(session)
        theorems = TheoremService(session)
        proofs = ProofService(session)

        x = register_term_var(symbols, "x")
        pred = register_prop_var(symbols, "P¹", arity=1)
        body = formulas.register([Token(symbol_id=pred.id), Token(symbol_id=x.id)])
        quantified = formulas.register(proofs.compute_gen_tokens(body.id, x.id))
        axiom = axioms.register("P_x", body.id)
        theorem = theorems.register("forall_x_Px", quantified.id)
        proof = proofs.create_proof(theorem.id)

        proofs.add_step(proof.id, AxiomStepInput(axiom.id), body.id)
        proofs.add_step(proof.id, GenStepInput(0, x.id), quantified.id)
        proofs.validate(proof.id)

        assert proofs.get(proof.id).status == "verified"


def test_add_raw_steps_batch_persists_and_validates_ordinary_steps() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        axioms = AxiomService(session)
        theorems = TheoremService(session)
        proofs = ProofService(session)

        x = register_term_var(symbols, "x")
        pred = register_prop_var(symbols, "P_batch", arity=1)
        body = formulas.register([Token(symbol_id=pred.id), Token(symbol_id=x.id)])
        quantified = formulas.register(proofs.compute_gen_tokens(body.id, x.id))
        axiom = axioms.register("P_batch_x", body.id)
        theorem = theorems.register("forall_x_P_batch_x", quantified.id)
        proof = proofs.create_proof(theorem.id)

        rows = proofs.add_raw_steps(
            proof.id,
            [
                (AxiomStepInput(axiom.id), body.id),
                (GenStepInput(0, x.id), quantified.id),
            ],
        )
        proofs.validate(proof.id)

        assert [row.ord for row in rows] == [0, 1]
        assert proofs.get(proof.id).status == "verified"

        # `add_raw_steps` handles each raw input kind explicitly and refuses
        # anything else outright, rather than silently storing a step it does
        # not understand. Until §6.2 removed it, `ComprehensionStepInput` was a
        # real input this rejected; with every remaining input kind raw, an
        # unrecognised object stands in for the next one someone adds.
        rejected_theorem = theorems.register("batch rejects unknown step input", body.id)
        rejected_proof = proofs.create_proof(rejected_theorem.id)
        with pytest.raises(TypeError, match="only ordinary raw proof inputs"):
            proofs.add_raw_steps(
                rejected_proof.id,
                [(object(), body.id)],  # type: ignore[list-item]
            )
        assert proofs.list_steps(rejected_proof.id) == []


def test_generalization_rejects_variable_free_in_premise() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        theorems = TheoremService(session)
        proofs = ProofService(session)

        x = register_term_var(symbols, "x")
        pred = register_prop_var(symbols, "P¹", arity=1)
        body = formulas.register([Token(symbol_id=pred.id), Token(symbol_id=x.id)])
        quantified = formulas.register(proofs.compute_gen_tokens(body.id, x.id))
        theorem = theorems.register("bad_gen", quantified.id, [body.id])
        proof = proofs.create_proof(theorem.id)

        proofs.add_step(proof.id, PremiseStepInput(0), body.id)
        with pytest.raises(ProofValidationError, match="Gen variable is free") as error:
            proofs.add_step(proof.id, GenStepInput(0, x.id), quantified.id)
        assert error.value.code == "proof.gen_variable_in_premise"
        assert len(proofs.list_steps(proof.id)) == 1
        assert proofs.get(proof.id).status == "draft"

        # The batch path still defers validation; the final validator must
        # continue to reject the same invalid proof independently.
        proofs.add_raw_steps(proof.id, [(GenStepInput(0, x.id), quantified.id)])
        with pytest.raises(ProofValidationError, match="Gen variable is free"):
            proofs.validate(proof.id)

        assert proofs.get(proof.id).status == "rejected"


def test_generalization_allows_variable_free_only_in_unused_premise() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        axioms = AxiomService(session)
        theorems = TheoremService(session)
        proofs = ProofService(session)

        x = register_term_var(symbols, "x")
        pred = register_prop_var(symbols, "P1", arity=1)
        q = register_prop_var(symbols, "Q")
        unused_premise = formulas.register([Token(symbol_id=pred.id), Token(symbol_id=x.id)])
        q_formula = formulas.register([Token(symbol_id=q.id)])
        quantified_q = formulas.register(proofs.compute_gen_tokens(q_formula.id, x.id))
        axiom = axioms.register("Q_axiom", q_formula.id)
        theorem = theorems.register("forall_q_from_unused_px", quantified_q.id, [unused_premise.id])
        proof = proofs.create_proof(theorem.id)

        proofs.add_step(proof.id, AxiomStepInput(axiom.id), q_formula.id)
        proofs.add_step(proof.id, GenStepInput(0, x.id), quantified_q.id)
        proofs.validate(proof.id)

        assert proofs.get(proof.id).status == "verified"


def test_generalization_rejects_variable_free_in_premise_via_transitive_dependency() -> None:
    """Regression test for dependency-based Gen: the free-in-premise check must
    follow premise_deps through an MP step, not just direct 'premise' steps.
    Body = MP(premise-derived antecedent, axiom-derived implication), so Gen
    must still see the premise dependency inherited through the union in the
    'rule' (MP) branch of validate_proof_step."""
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        axioms = AxiomService(session)
        theorems = TheoremService(session)
        proofs = ProofService(session)

        imp = symbols.get_by_role("implication")
        x = register_term_var(symbols, "x")
        pred = register_prop_var(symbols, "P1", arity=1)
        q = register_prop_var(symbols, "Q1", arity=1)

        premise_formula = formulas.register([Token(symbol_id=pred.id), Token(symbol_id=x.id)])
        q_x_formula = formulas.register([Token(symbol_id=q.id), Token(symbol_id=x.id)])
        implication_formula = formulas.register(
            [
                Token(symbol_id=imp.id),
                Token(symbol_id=pred.id),
                Token(symbol_id=x.id),
                Token(symbol_id=q.id),
                Token(symbol_id=x.id),
            ]
        )
        quantified_q = formulas.register(proofs.compute_gen_tokens(q_x_formula.id, x.id))
        axiom = axioms.register("P_implies_Q", implication_formula.id)
        theorem = theorems.register(
            "bad_gen_transitive", quantified_q.id, [premise_formula.id]
        )
        proof = proofs.create_proof(theorem.id)

        proofs.add_step(proof.id, PremiseStepInput(0), premise_formula.id)
        proofs.add_step(proof.id, AxiomStepInput(axiom.id), implication_formula.id)
        proofs.add_step(proof.id, MPStepInput(0, 1), q_x_formula.id)
        with pytest.raises(ProofValidationError, match="Gen variable is free") as error:
            proofs.add_step(proof.id, GenStepInput(2, x.id), quantified_q.id)
        assert error.value.code == "proof.gen_variable_in_premise"
        assert len(proofs.list_steps(proof.id)) == 3
        assert proofs.get(proof.id).status == "draft"

        # The batch path still defers validation; the final validator must
        # continue to reject the same invalid proof independently.
        proofs.add_raw_steps(proof.id, [(GenStepInput(2, x.id), quantified_q.id)])
        with pytest.raises(ProofValidationError, match="Gen variable is free"):
            proofs.validate(proof.id)

        assert proofs.get(proof.id).status == "rejected"


def test_theorem_step_applies_verified_pinned_proof() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        theorems = TheoremService(session)
        proofs = ProofService(session)

        phi = register_prop_var(symbols, "φ")
        psi = register_prop_var(symbols, "ψ")
        phi_formula = formulas.register([Token(symbol_id=phi.id)])
        psi_formula = formulas.register([Token(symbol_id=psi.id)])

        source_theorem = theorems.register("phi_from_phi", phi_formula.id, [phi_formula.id])
        source_proof = proofs.create_proof(source_theorem.id)
        proofs.add_step(source_proof.id, PremiseStepInput(0), phi_formula.id)
        proofs.validate(source_proof.id)

        target_theorem = theorems.register("psi_from_psi", psi_formula.id, [psi_formula.id])
        target_proof = proofs.create_proof(target_theorem.id)
        subst = Substitution(prop_substs=(PropSubst(phi.id, psi_formula.id),))
        proofs.add_step(target_proof.id, PremiseStepInput(0), psi_formula.id)
        proofs.add_step(
            target_proof.id,
            TheoremStepInput(source_proof.id, subst, arg_step_ords=(0,)),
            psi_formula.id,
        )
        proofs.validate(target_proof.id)

        assert proofs.get(target_proof.id).status == "verified"


def test_phi_implies_phi_hilbert_proof_validates_and_tracks_axioms() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        axioms = AxiomService(session)
        theorems = TheoremService(session)
        proofs = ProofService(session)

        imp = symbols.get_by_role("implication")
        phi = register_prop_var(symbols, "φ")
        psi = register_prop_var(symbols, "ψ")
        chi = register_prop_var(symbols, "χ")

        phi_formula = formulas.register([Token(symbol_id=phi.id)])
        phi_to_phi = formulas.register([Token(symbol_id=imp.id), Token(symbol_id=phi.id), Token(symbol_id=phi.id)])

        k_formula = formulas.register(
            [
                Token(symbol_id=imp.id),
                Token(symbol_id=phi.id),
                Token(symbol_id=imp.id),
                Token(symbol_id=psi.id),
                Token(symbol_id=phi.id),
            ]
        )
        s_formula = formulas.register(
            [
                Token(symbol_id=imp.id),
                Token(symbol_id=imp.id),
                Token(symbol_id=phi.id),
                Token(symbol_id=imp.id),
                Token(symbol_id=psi.id),
                Token(symbol_id=chi.id),
                Token(symbol_id=imp.id),
                Token(symbol_id=imp.id),
                Token(symbol_id=phi.id),
                Token(symbol_id=psi.id),
                Token(symbol_id=imp.id),
                Token(symbol_id=phi.id),
                Token(symbol_id=chi.id),
            ]
        )
        k_axiom = axioms.register("K", k_formula.id)
        s_axiom = axioms.register("S", s_formula.id)

        theorem = theorems.register("phi_to_phi", phi_to_phi.id)
        proof = proofs.create_proof(theorem.id)

        sigma0 = Substitution(
            prop_substs=(
                PropSubst(chi.id, phi_formula.id),
                PropSubst(psi.id, phi_to_phi.id),
            )
        )
        step0 = formulas.register(proofs.compute_substituted_tokens(s_axiom.formula_id, sigma0))
        proofs.add_step(proof.id, AxiomStepInput(s_axiom.id, sigma0), step0.id)

        sigma1 = Substitution(prop_substs=(PropSubst(psi.id, phi_to_phi.id),))
        step1 = formulas.register(proofs.compute_substituted_tokens(k_axiom.formula_id, sigma1))
        proofs.add_step(proof.id, AxiomStepInput(k_axiom.id, sigma1), step1.id)

        step2 = formulas.register(
            [
                Token(symbol_id=imp.id),
                Token(symbol_id=imp.id),
                Token(symbol_id=phi.id),
                Token(symbol_id=imp.id),
                Token(symbol_id=phi.id),
                Token(symbol_id=phi.id),
                Token(symbol_id=imp.id),
                Token(symbol_id=phi.id),
                Token(symbol_id=phi.id),
            ]
        )
        proofs.add_step(proof.id, MPStepInput(1, 0), step2.id)

        sigma3 = Substitution(prop_substs=(PropSubst(psi.id, phi_formula.id),))
        step3 = formulas.register(proofs.compute_substituted_tokens(k_axiom.formula_id, sigma3))
        proofs.add_step(proof.id, AxiomStepInput(k_axiom.id, sigma3), step3.id)

        proofs.add_step(proof.id, MPStepInput(3, 2), phi_to_phi.id)
        proofs.validate(proof.id)

        reconstructed, _ = proofs.reconstruct_steps(proof.id)[0]
        assert [
            item.source_symbol_id for item in reconstructed.subst.prop_substs
        ] == sorted((psi.id, chi.id))

        prop_system = axioms.register_system("propositional_core")
        k_only = axioms.register_system("k_only")
        axioms.add_to_system(prop_system.id, k_axiom.id)
        axioms.add_to_system(prop_system.id, s_axiom.id)
        axioms.add_to_system(k_only.id, k_axiom.id)

        assert proofs.get(proof.id).status == "verified"
        assert theorems.get(theorem.id).status == "proven"
        assert [axiom.name for axiom in proofs.list_used_axioms(proof.id)] == ["K", "S"]
        assert proofs.is_valid_in_system(proof.id, prop_system.id) is True
        assert proofs.is_valid_in_system(proof.id, k_only.id) is False
        assert [t.name for t in axioms.list_theorems_provable_in_system(prop_system.id)] == ["phi_to_phi"]
        assert axioms.list_theorems_provable_in_system(k_only.id) == []


def test_list_used_in_theorems_finds_direct_axiom_and_lemma_citations() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        axioms = AxiomService(session)
        theorems = TheoremService(session)
        proofs = ProofService(session)

        prop = register_prop_var(symbols, "φ")
        prop_formula = formulas.register([Token(symbol_id=prop.id)])

        axiom = axioms.register("phi_axiom", prop_formula.id)
        unused_axiom = axioms.register("unused_axiom", prop_formula.id)

        lemma = theorems.register("phi_lemma", prop_formula.id)
        lemma_proof = proofs.create_proof(lemma.id)
        proofs.add_step(lemma_proof.id, AxiomStepInput(axiom.id), prop_formula.id)
        proofs.validate(lemma_proof.id)

        main_theorem = theorems.register("phi_main", prop_formula.id)
        main_proof = proofs.create_proof(main_theorem.id)
        proofs.add_step(main_proof.id, TheoremStepInput(lemma_proof.id), prop_formula.id)

        assert [t.name for t in axioms.list_used_in_theorems(axiom.id)] == ["phi_lemma"]
        assert axioms.list_used_in_theorems(unused_axiom.id) == []
        assert [t.name for t in theorems.list_used_in_theorems(lemma.id)] == ["phi_main"]
        assert theorems.list_used_in_theorems(main_theorem.id) == []


def test_add_step_rejects_invalid_substitution_shape() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        axioms = AxiomService(session)
        theorems = TheoremService(session)
        proofs = ProofService(session)

        x = register_term_var(symbols, "x")
        prop = register_prop_var(symbols, "φ")
        prop_formula = formulas.register([Token(symbol_id=prop.id)])
        axiom = axioms.register("phi", prop_formula.id)
        theorem = theorems.register("phi", prop_formula.id)
        proof = proofs.create_proof(theorem.id)

        bad_subst = Substitution(prop_substs=(PropSubst(prop.id, prop_formula.id, (x.id,)),))
        with pytest.raises(ValidationError, match="formal parameter count mismatch"):
            proofs.add_step(proof.id, AxiomStepInput(axiom.id, bad_subst), prop_formula.id)


def test_add_step_interns_an_omitted_derived_conclusion() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        axioms = AxiomService(session)
        theorems = TheoremService(session)
        proofs = ProofService(session)

        prop = register_prop_var(symbols, "φ")
        prop_formula = formulas.register([Token(symbol_id=prop.id)])
        axiom = axioms.register("phi", prop_formula.id)
        theorem = theorems.register("phi", prop_formula.id)
        proof = proofs.create_proof(theorem.id)

        step = proofs.add_step(proof.id, AxiomStepInput(axiom.id))
        assert step.conclusion_formula_id == prop_formula.id


def test_assumption_step_still_requires_a_conclusion() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        theorems = TheoremService(session)
        proofs = ProofService(session)

        prop = register_prop_var(symbols, "φ")
        prop_formula = formulas.register([Token(symbol_id=prop.id)])
        theorem = theorems.register("phi", prop_formula.id)
        proof = proofs.create_proof(theorem.id)

        with pytest.raises(ValidationError) as caught:
            proofs.add_step(proof.id, AssumptionStepInput())
        assert caught.value.code == "proof.assumption_needs_conclusion"


def test_step_suggestion_recovers_substitution_and_argument_candidate() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        theorems = TheoremService(session)
        proofs = ProofService(session)

        phi = register_prop_var(symbols, "φ")
        psi = register_prop_var(symbols, "ψ")
        phi_formula = formulas.register([Token(symbol_id=phi.id)])
        psi_formula = formulas.register([Token(symbol_id=psi.id)])

        lemma = theorems.register("identity_schema", phi_formula.id, [phi_formula.id])
        lemma_proof = proofs.create_proof(lemma.id)
        proofs.add_step(lemma_proof.id, PremiseStepInput(0))
        proofs.validate(lemma_proof.id)

        target = theorems.register("target", psi_formula.id, [psi_formula.id])
        target_proof = proofs.create_proof(target.id)
        proofs.add_step(target_proof.id, PremiseStepInput(0))
        result = proofs.suggest_step(
            target_proof.id,
            kind="theorem",
            applied_theorem_id=lemma.id,
            arg_step_ords=(0,),
            goal_tokens=[Token(symbol_id=psi.id)],
        )

        assert result["arg_candidates"] == [[0]]
        assert result["conclusion_tokens"] == [Token(symbol_id=psi.id)]
        subst = result["subst"]
        assert len(subst.prop_substs) == 1
        assert formulas.get_tokens(subst.prop_substs[0].body_formula_id)[0].symbol_id == psi.id


def test_step_suggestion_materializes_unary_miller_pattern() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        axioms = AxiomService(session)
        theorems = TheoremService(session)
        proofs = ProofService(session)

        x = register_term_var(symbols, "x")
        y = register_term_var(symbols, "y")
        phi1 = register_prop_var(symbols, "φ¹", arity=1)
        predicate_type = symbols.get_symbol_type_by_name(SymbolTypeName.PREDICATE.value)
        predicate = symbols.register("P", predicate_type.id, 1)
        universal = symbols.get_by_role("universal_quantifier")
        equality = symbols.get_by_role("equality")
        pattern = formulas.register(
            [Token(symbol_id=universal.id), Token(symbol_id=phi1.id), Token(de_bruijn_index=0)]
        )
        goal_tokens = [
            Token(symbol_id=universal.id),
            Token(symbol_id=equality.id),
            Token(de_bruijn_index=0),
            Token(symbol_id=x.id),
        ]
        goal = formulas.register(goal_tokens)
        axiom = axioms.register("forall_schema", pattern.id)
        theorem = theorems.register("target", goal.id)
        proof = proofs.create_proof(theorem.id)

        result = proofs.suggest_step(
            proof.id,
            kind="axiom",
            axiom_id=axiom.id,
            goal_tokens=goal_tokens,
        )

        assert result["conclusion_tokens"] == goal_tokens
        subst = result["subst"]
        assert len(subst.prop_substs) == 1
        assert len(subst.prop_substs[0].formal_param_symbol_ids) == 1
        body = formulas.get_tokens(subst.prop_substs[0].body_formula_id)
        assert body[0].symbol_id == equality.id
        assert body[1].symbol_id == y.id
        assert body[2].symbol_id == x.id
        assert subst.prop_substs[0].formal_param_symbol_ids == (y.id,)
