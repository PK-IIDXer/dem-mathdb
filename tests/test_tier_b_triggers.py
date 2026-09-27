"""Tier B formula validation and immutability across both SQL dialects."""

from __future__ import annotations

import os
import random
from collections import defaultdict
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dem.db.models import Formula, FormulaToken, Symbol
from dem.db.triggers import (
    POSTGRES_TIER_B_TRIGGER_SPECS,
    SQLITE_TIER_B_TRIGGER_SPECS,
    TIER_A_TRIGGER_SPECS,
    TIER_B_IMMUTABILITY_TRIGGER_SPECS,
    formula_is_wellformed,
    incomplete_formulas,
)
from dem.services.formula import validate_tokens
from dem.types import FormulaTypeName, SymbolMeta, SymbolTypeName, Token


SEED_PHASE = "l2"
_TEST_DATABASE_ENV = "DEM_TEST_DATABASE"


def _formula_type_id(session: Session, code: str) -> int:
    formula_type_id = session.scalar(
        text("SELECT id FROM formula_type WHERE code = :code"), {"code": code}
    )
    assert formula_type_id is not None
    return formula_type_id


def _symbol_id(session: Session, name: str) -> int:
    symbol_id = session.scalar(
        text("SELECT id FROM symbol WHERE name = :name ORDER BY id LIMIT 1"),
        {"name": name},
    )
    assert symbol_id is not None
    return symbol_id


def _insert_formula(
    session: Session,
    *,
    formula_type_id: int,
    tokens: list[dict[str, int | None]],
    token_count: int | None = None,
    order: list[int] | None = None,
) -> int:
    formula_id = session.scalar(
        text(
            "INSERT INTO formula "
            "(public_id, formula_type_id, hash, token_count) "
            "VALUES (:public_id, :formula_type_id, :hash, :token_count) "
            "RETURNING id"
        ),
        {
            "public_id": str(uuid4()),
            "formula_type_id": formula_type_id,
            "hash": uuid4().hex,
            "token_count": token_count if token_count is not None else len(tokens),
        },
    )
    assert formula_id is not None
    positions = order if order is not None else list(range(len(tokens)))
    for position in positions:
        session.execute(
            text(
                "INSERT INTO formula_token "
                "(formula_id, position, symbol_id, de_bruijn_index) "
                "VALUES (:formula_id, :position, :symbol_id, :de_bruijn_index)"
            ),
            {
                "formula_id": formula_id,
                "position": position,
                **tokens[position],
            },
        )
    return formula_id


def _force_deferred_check(session: Session) -> None:
    if session.get_bind().dialect.name == "postgresql":
        session.execute(
            text("SET CONSTRAINTS formula_wellformed_deferred_insert IMMEDIATE")
        )


def _assert_rejected(
    session: Session,
    *,
    formula_type_id: int,
    tokens: list[dict[str, int | None]],
    token_count: int | None = None,
) -> None:
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            _insert_formula(
                session,
                formula_type_id=formula_type_id,
                tokens=tokens,
                token_count=token_count,
            )
            _force_deferred_check(session)


def test_database_and_python_agree_for_every_l2_formula(seeded_session: Session) -> None:
    symbols = list(seeded_session.scalars(select(Symbol).order_by(Symbol.id)))
    symbol_meta = {
        symbol.id: SymbolMeta(
            arity=symbol.arity,
            symbol_type_name=SymbolTypeName(symbol.symbol_type.name),
            output_formula_type=FormulaTypeName(
                symbol.symbol_type.output_formula_type.name
            ),
            input_formula_type=(
                FormulaTypeName(symbol.symbol_type.input_formula_type.name)
                if symbol.symbol_type.input_formula_type is not None
                else None
            ),
            is_quantifier=symbol.symbol_type.is_quantifier,
        )
        for symbol in symbols
    }
    tokens_by_formula: dict[int, list[Token]] = defaultdict(list)
    for row in seeded_session.scalars(
        select(FormulaToken).order_by(FormulaToken.formula_id, FormulaToken.position)
    ):
        tokens_by_formula[row.formula_id].append(
            Token(symbol_id=row.symbol_id)
            if row.symbol_id is not None
            else Token(de_bruijn_index=row.de_bruijn_index)
        )

    formulas = list(seeded_session.scalars(select(Formula).order_by(Formula.id)))
    mismatches: list[int] = []
    connection = seeded_session.connection()
    for formula in formulas:
        python_type = validate_tokens(tokens_by_formula[formula.id], symbol_meta)
        if (
            python_type != FormulaTypeName(formula.formula_type.name)
            or not formula_is_wellformed(connection, formula.id)
        ):
            mismatches.append(formula.id)

    assert len(formulas) == 8
    assert mismatches == []


@pytest.mark.parametrize("order_kind", ["forward", "reverse", "random"])
def test_sqlite_gate_does_not_depend_on_insert_order(
    fresh_seeded_session: Session, order_kind: str
) -> None:
    if fresh_seeded_session.get_bind().dialect.name != "sqlite":
        pytest.skip("SQLite insertion-order contract")
    implies = _symbol_id(fresh_seeded_session, "→")
    bottom = _symbol_id(fresh_seeded_session, "⊥")
    tokens = [
        {"symbol_id": implies, "de_bruijn_index": None},
        {"symbol_id": bottom, "de_bruijn_index": None},
        {"symbol_id": bottom, "de_bruijn_index": None},
    ]
    order = list(range(len(tokens)))
    if order_kind == "reverse":
        order.reverse()
    elif order_kind == "random":
        random.Random(20260918).shuffle(order)

    with fresh_seeded_session.begin_nested():
        formula_id = _insert_formula(
            fresh_seeded_session,
            formula_type_id=_formula_type_id(
                fresh_seeded_session, "proposition"
            ),
            tokens=tokens,
            order=order,
        )
        assert formula_is_wellformed(
            fresh_seeded_session.connection(), formula_id
        )


def test_malformed_formula_shapes_are_rejected(
    fresh_seeded_session: Session,
) -> None:
    proposition_type = _formula_type_id(fresh_seeded_session, "proposition")
    term_type = _formula_type_id(fresh_seeded_session, "term")
    implies = _symbol_id(fresh_seeded_session, "→")
    bottom = _symbol_id(fresh_seeded_session, "⊥")
    equality = _symbol_id(fresh_seeded_session, "=")

    # Missing the implication's final child while claiming the row is complete.
    _assert_rejected(
        fresh_seeded_session,
        formula_type_id=proposition_type,
        tokens=[
            {"symbol_id": implies, "de_bruijn_index": None},
            {"symbol_id": bottom, "de_bruijn_index": None},
        ],
    )
    # A complete nullary proposition followed by an extra token.
    _assert_rejected(
        fresh_seeded_session,
        formula_type_id=proposition_type,
        tokens=[
            {"symbol_id": bottom, "de_bruijn_index": None},
            {"symbol_id": bottom, "de_bruijn_index": None},
        ],
    )
    _assert_rejected(
        fresh_seeded_session,
        formula_type_id=term_type,
        tokens=[{"symbol_id": None, "de_bruijn_index": 99}],
    )
    _assert_rejected(
        fresh_seeded_session,
        formula_type_id=proposition_type,
        tokens=[
            {"symbol_id": equality, "de_bruijn_index": None},
            {"symbol_id": bottom, "de_bruijn_index": None},
            {"symbol_id": bottom, "de_bruijn_index": None},
        ],
    )
    _assert_rejected(
        fresh_seeded_session,
        formula_type_id=term_type,
        tokens=[{"symbol_id": bottom, "de_bruijn_index": None}],
    )


def test_missing_symbol_is_rejected_by_foreign_key(
    fresh_seeded_session: Session,
) -> None:
    missing_symbol = fresh_seeded_session.scalar(
        text("SELECT COALESCE(MAX(id), 0) + 1000000 FROM symbol")
    )
    assert missing_symbol is not None
    _assert_rejected(
        fresh_seeded_session,
        formula_type_id=_formula_type_id(
            fresh_seeded_session, "proposition"
        ),
        tokens=[{"symbol_id": missing_symbol, "de_bruijn_index": None}],
    )


def test_incomplete_formula_commit_contract(fresh_seeded_session: Session) -> None:
    database_url = fresh_seeded_session.get_bind().engine.url
    engine = create_engine(database_url)
    bottom = _symbol_id(fresh_seeded_session, "⊥")
    proposition_type = _formula_type_id(fresh_seeded_session, "proposition")
    formula_id: int | None = None
    try:
        with Session(engine) as independent:
            formula_id = _insert_formula(
                independent,
                formula_type_id=proposition_type,
                tokens=[{"symbol_id": bottom, "de_bruijn_index": None}],
                token_count=2,
            )
            if engine.dialect.name == "postgresql":
                with pytest.raises(IntegrityError, match="not well-formed"):
                    independent.commit()
                independent.rollback()
            else:
                independent.commit()
                assert incomplete_formulas(independent.connection()) == [
                    (formula_id, 2, 1)
                ]
                independent.execute(
                    text("DELETE FROM formula_token WHERE formula_id = :formula_id"),
                    {"formula_id": formula_id},
                )
                independent.execute(
                    text("DELETE FROM formula WHERE id = :formula_id"),
                    {"formula_id": formula_id},
                )
                independent.commit()
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("column", "value_sql"),
    [
        ("public_id", "'changed-public-id'"),
        ("hash", "'changed-hash'"),
        ("formula_type_id", "formula_type_id + 1"),
        ("token_count", "token_count + 1"),
    ],
)
def test_formula_identity_columns_are_immutable(
    fresh_seeded_session: Session, column: str, value_sql: str
) -> None:
    formula_id = fresh_seeded_session.scalar(
        text("SELECT id FROM formula ORDER BY id LIMIT 1")
    )
    assert formula_id is not None
    with pytest.raises(IntegrityError, match="formula identity is immutable"):
        with fresh_seeded_session.begin_nested():
            fresh_seeded_session.execute(
                text(
                    f"UPDATE formula SET {column} = {value_sql} "
                    "WHERE id = :formula_id"
                ),
                {"formula_id": formula_id},
            )


@pytest.mark.parametrize("operation", ["insert", "update", "delete"])
def test_completed_formula_tokens_are_immutable(
    fresh_seeded_session: Session, operation: str
) -> None:
    token = fresh_seeded_session.execute(
        text(
            "SELECT formula_id, id, position FROM formula_token "
            "ORDER BY formula_id, position LIMIT 1"
        )
    ).mappings().one()
    with pytest.raises(IntegrityError, match="completed formula tokens are immutable"):
        with fresh_seeded_session.begin_nested():
            if operation == "insert":
                fresh_seeded_session.execute(
                    text(
                        "INSERT INTO formula_token "
                        "(formula_id, position, de_bruijn_index) "
                        "VALUES (:formula_id, 1000000, 0)"
                    ),
                    dict(token),
                )
            elif operation == "update":
                fresh_seeded_session.execute(
                    text(
                        "UPDATE formula_token SET position = position "
                        "WHERE id = :id"
                    ),
                    dict(token),
                )
            else:
                fresh_seeded_session.execute(
                    text("DELETE FROM formula_token WHERE id = :id"), dict(token)
                )


def test_completed_formula_cannot_be_deleted(
    fresh_seeded_session: Session,
) -> None:
    formula_id = fresh_seeded_session.scalar(
        text("SELECT id FROM formula ORDER BY id LIMIT 1")
    )
    assert formula_id is not None
    with pytest.raises(IntegrityError, match="completed formula cannot be deleted"):
        with fresh_seeded_session.begin_nested():
            fresh_seeded_session.execute(
                text("DELETE FROM formula WHERE id = :formula_id"),
                {"formula_id": formula_id},
            )


@pytest.mark.parametrize(
    ("column", "value_sql"),
    [
        ("public_id", "'changed-symbol-public-id'"),
        ("symbol_type_id", "symbol_type_id + 1"),
        ("arity", "arity + 1"),
    ],
)
def test_symbol_identity_and_shape_are_immutable(
    fresh_seeded_session: Session, column: str, value_sql: str
) -> None:
    symbol_id = fresh_seeded_session.scalar(
        text("SELECT symbol_id FROM formula_token WHERE symbol_id IS NOT NULL LIMIT 1")
    )
    assert symbol_id is not None
    with pytest.raises(IntegrityError, match="symbol identity and shape are immutable"):
        with fresh_seeded_session.begin_nested():
            fresh_seeded_session.execute(
                text(
                    f"UPDATE symbol SET {column} = {value_sql} "
                    "WHERE id = :symbol_id"
                ),
                {"symbol_id": symbol_id},
            )


@pytest.mark.parametrize(
    ("table", "assignment", "message"),
    [
        (
            "formula_type",
            "code = CASE code WHEN 'term' THEN 'proposition' ELSE 'term' END",
            "formula type semantics are immutable",
        ),
        (
            "symbol_type",
            "is_quantifier = CASE WHEN is_quantifier THEN false ELSE true END",
            "symbol type semantics are immutable",
        ),
    ],
)
def test_parser_type_semantics_are_immutable(
    fresh_seeded_session: Session,
    table: str,
    assignment: str,
    message: str,
) -> None:
    with pytest.raises(IntegrityError, match=message):
        with fresh_seeded_session.begin_nested():
            fresh_seeded_session.execute(
                text(
                    f"UPDATE {table} SET {assignment} "
                    f"WHERE id = (SELECT MIN(id) FROM {table})"
                )
            )


def test_display_metadata_updates_remain_allowed(
    fresh_seeded_session: Session,
) -> None:
    symbol_id = fresh_seeded_session.scalar(
        text(
            "SELECT id FROM symbol WHERE arity = 2 "
            "AND notation_kind = 'infix' ORDER BY id LIMIT 1"
        )
    )
    formula_id = fresh_seeded_session.scalar(
        text("SELECT id FROM formula ORDER BY id LIMIT 1")
    )
    assert symbol_id is not None and formula_id is not None
    with fresh_seeded_session.begin_nested():
        fresh_seeded_session.execute(
            text(
                "UPDATE symbol SET remarks = 'updated', "
                "latex_template = 'tier-b-display', "
                "notation_kind = 'prefix', precedence = NULL "
                "WHERE id = :symbol_id"
            ),
            {"symbol_id": symbol_id},
        )
        fresh_seeded_session.execute(
            text(
                "UPDATE formula SET description = 'updated', remarks = 'updated' "
                "WHERE id = :formula_id"
            ),
            {"formula_id": formula_id},
        )
        fresh_seeded_session.flush()


def test_tier_b_trigger_sets_match_schema_origins(seed_snapshot_factory) -> None:
    database = os.environ.get(_TEST_DATABASE_ENV, "sqlite").lower()
    dialect_specs = (
        SQLITE_TIER_B_TRIGGER_SPECS
        if database == "sqlite"
        else POSTGRES_TIER_B_TRIGGER_SPECS
    )
    expected = {
        spec.name
        for spec in (
            *TIER_A_TRIGGER_SPECS,
            *dialect_specs,
            *TIER_B_IMMUTABILITY_TRIGGER_SPECS,
        )
    }
    with seed_snapshot_factory.l2_origin_urls(database) as urls:
        for database_url in urls:
            engine = create_engine(database_url)
            try:
                with engine.connect() as connection:
                    if database == "sqlite":
                        actual = set(
                            connection.scalars(
                                text(
                                    "SELECT name FROM sqlite_master "
                                    "WHERE type = 'trigger'"
                                )
                            )
                        )
                    else:
                        actual = set(
                            connection.scalars(
                                text(
                                    "SELECT tgname FROM pg_trigger "
                                    "WHERE NOT tgisinternal"
                                )
                            )
                        )
                    assert actual == expected
            finally:
                engine.dispose()
