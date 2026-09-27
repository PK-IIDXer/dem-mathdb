from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from dem.db.models import Base
from dem.db.seed import seed_language
from dem.errors import NotFoundError
from dem.services.definition import DefinitionService
from dem.services.formula import FormulaService
from dem.services.symbol import SymbolService
from dem.types import SymbolTypeName, Token


def make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_language(session)
    return session


def formula_tokens(formulas: FormulaService, formula_id: int) -> list[Token]:
    return [
        Token(symbol_id=row.symbol_id)
        if row.symbol_id is not None
        else Token(de_bruijn_index=row.de_bruijn_index)
        for row in formulas.get_tokens(formula_id)
    ]


def test_symbol_roles_are_seeded() -> None:
    with make_session() as session:
        symbols = SymbolService(session)

        assert symbols.get_by_role("implication").name == "→"
        assert symbols.get_by_role("universal_quantifier").name == "∀"
        assert symbols.get_by_role("biconditional").name == "↔"
        assert symbols.get_by_role("equality").name == "="


def test_common_logical_symbols_are_primitive() -> None:
    # The public language treats these connectives as primitive infrastructure.
    with make_session() as session:
        symbols = SymbolService(session)
        definitions = DefinitionService(session)

        for name in ("∧", "→", "∃"):
            symbol = symbols.get_by_name(name)
            assert symbol.is_primitive is True
            with pytest.raises(NotFoundError):
                definitions.get_by_name(name)

        assert symbols.get_by_role("implication").name == "→"


def test_seed_language_repairs_existing_primitive_symbol_display_metadata() -> None:
    with make_session() as session:
        symbols = SymbolService(session)

        for name in ("∨", "↔", "="):
            symbol = symbols.get_by_name(name)
            symbol.notation_kind = "prefix"
            symbol.precedence = None
            symbol.latex_template = None
        session.flush()

        seed_language(session)

        expected = {
            "∨": ("infix", 30, r"\vee"),
            "↔": ("infix", 10, r"\iff"),
            "=": ("infix", 100, "="),
        }
        for name, (notation_kind, precedence, latex_template) in expected.items():
            symbol = symbols.get_by_name(name)
            assert symbol.notation_kind == notation_kind
            assert symbol.precedence == precedence
            assert symbol.latex_template == latex_template


def test_formula_registration_deduplicates_by_hash() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        prop_var_type = symbols.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value)
        phi = symbols.register("φ", prop_var_type.id, 0)
        implies = symbols.get_by_role("implication")

        tokens = [Token(symbol_id=implies.id), Token(symbol_id=phi.id), Token(symbol_id=phi.id)]
        first = formulas.register(tokens, remarks="φ→φ")
        second = formulas.register(tokens, remarks="duplicate")

        assert first.id == second.id
        assert first.token_count == 3
        assert [row.position for row in formulas.get_tokens(first.id)] == [0, 1, 2]


def test_associativity_formula_can_be_registered() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)

        term_var_type = symbols.get_symbol_type_by_name(SymbolTypeName.FREE_TERM_VAR.value)
        function_type = symbols.get_symbol_type_by_name(SymbolTypeName.FUNCTION.value)
        g = symbols.register("G", term_var_type.id, 0)
        dot = symbols.register("·", function_type.id, 2, is_primitive=True)

        forall = symbols.get_by_role("universal_quantifier")
        equality = symbols.get_by_role("equality")

        tokens = [
            Token(symbol_id=forall.id),
            Token(symbol_id=forall.id),
            Token(symbol_id=forall.id),
            Token(symbol_id=equality.id),
            Token(symbol_id=dot.id),
            Token(de_bruijn_index=2),
            Token(symbol_id=dot.id),
            Token(de_bruijn_index=1),
            Token(de_bruijn_index=0),
            Token(symbol_id=dot.id),
            Token(symbol_id=dot.id),
            Token(de_bruijn_index=2),
            Token(de_bruijn_index=1),
            Token(de_bruijn_index=0),
        ]

        formula = formulas.register(tokens, remarks="結合法則")

        assert formula.token_count == len(tokens)
        assert formula.formula_type.name == "命題"


def test_mixed_formula_tokens_are_inserted_in_one_statement() -> None:
    with make_session() as session:
        symbols = SymbolService(session)
        formulas = FormulaService(session)
        term_var_type = symbols.get_symbol_type_by_name(
            SymbolTypeName.FREE_TERM_VAR.value
        )
        free_term = symbols.register("batch_x", term_var_type.id, 0)
        forall = symbols.get_by_role("universal_quantifier")
        equality = symbols.get_by_role("equality")
        tokens = [
            Token(symbol_id=forall.id),
            Token(symbol_id=equality.id),
            Token(de_bruijn_index=0),
            Token(symbol_id=free_term.id),
        ]
        token_inserts: list[tuple[bool, list[dict[str, object]]]] = []

        @event.listens_for(session.get_bind(), "before_cursor_execute")
        def capture_token_insert(
            _connection, _cursor, statement, _parameters, context, executemany
        ) -> None:
            if statement.lstrip().startswith("INSERT INTO formula_token"):
                token_inserts.append(
                    (bool(executemany), list(context.compiled_parameters))
                )

        formula = formulas.register(tokens)

        assert len(token_inserts) == 1
        executemany, parameters = token_inserts[0]
        assert executemany is True
        assert len(parameters) == len(tokens)
        assert all(
            {"formula_id", "position", "symbol_id", "de_bruijn_index"}
            <= parameter.keys()
            for parameter in parameters
        )
        assert [row.position for row in formulas.get_tokens(formula.id)] == list(
            range(len(tokens))
        )
        assert formula_tokens(formulas, formula.id) == tokens
