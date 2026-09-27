"""Seed rows before 20260910_0002 and check its upgrade/downgrade on DEM_DATABASE_URL.

Run inside the API image with the script on stdin:
    python - seed         # at 20260910_0001
    python - check-head   # after `alembic upgrade head`
    python - check-base   # after `alembic downgrade 20260910_0001`

An empty database never executes the per-row UPDATEs, so seed enough rows
(bound variables, several proofs per theorem) to exercise every bound statement.

The rows must also be what the seed would produce: the formula types are named
項 / 命題 (20260918_0003 maps them to stable codes and refuses anything else), and
every formula is well-formed (20260918_0004 re-checks all existing formulas before
installing the Tier B gate). Symbols therefore carry real arities and input types,
and bound indices only occur under a quantifier.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
import sys
from uuid import UUID

import sqlalchemy as sa

from dem.identity import DEFAULT_NAMESPACE_NAME, deterministic_public_id

# formula_type ids as seeded by dem.db.seed.seed_language.
TERM_TYPE, PROPOSITION_TYPE = 1, 2
# symbol_type id -> (name, input formula type, fixed arity, is_quantifier); all output propositions.
SYMBOL_TYPES = {
    1: ("ci-prop-atom", None, 0, False),
    2: ("ci-predicate", TERM_TYPE, None, False),
    3: ("ci-connective", PROPOSITION_TYPE, None, False),
    4: ("ci-quantifier", PROPOSITION_TYPE, 1, True),
}
# (id, name) and symbol id -> (symbol_type id, arity).
SYMBOLS = [(1, "p"), (2, "q"), (3, "r"), (4, "and"), (5, "all")]
SYMBOL_SHAPES = {1: (1, 0), 2: (1, 0), 3: (2, 1), 4: (3, 2), 5: (4, 1)}
# formula id -> tokens; an int is a symbol id, ("B", n) a bound index (a term).
FORMULAS = {
    1: [1],  # p
    2: [2],  # q
    3: [4, 1, 2],  # p and q
    4: [5, 3, ("B", 0)],  # all x. r(x)
    5: [5, 5, 4, 3, ("B", 1), 3, ("B", 0)],  # all x. all y. r(x) and r(y)
}
THEOREMS = [(2, "t_two", 3), (1, "t_one", 4)]
PROOFS = [(5, 2), (1, 1), (3, 2), (2, 1), (4, 2)]


def seed(connection) -> None:
    # Timestamps are bound explicitly: the migrated server default is now(),
    # which PostgreSQL accepts but SQLite (used to try this script locally) does not.
    now = datetime(2026, 9, 14, tzinfo=timezone.utc).replace(tzinfo=None)

    def run(sql, rows):
        connection.execute(sa.text(sql), [{"now": now, **row} for row in rows])

    run(
        "INSERT INTO formula_type (id, name, created_at) VALUES (:id, :name, :now)",
        [{"id": TERM_TYPE, "name": "項"}, {"id": PROPOSITION_TYPE, "name": "命題"}],
    )
    run(
        "INSERT INTO symbol_type (id, name, output_formula_type_id, input_formula_type_id, "
        "fixed_arity, is_quantifier, created_at) "
        "VALUES (:id, :name, :output, :input, :arity, :q, :now)",
        [
            {"id": i, "name": n, "output": PROPOSITION_TYPE, "input": inp, "arity": a, "q": q}
            for i, (n, inp, a, q) in SYMBOL_TYPES.items()
        ],
    )
    run(
        "INSERT INTO symbol (id, name, symbol_type_id, arity, is_primitive, notation_kind, "
        "usage_count, created_at) VALUES (:id, :name, :type, :arity, :prim, 'prefix', 0, :now)",
        [
            {"id": i, "name": n, "type": SYMBOL_SHAPES[i][0], "arity": SYMBOL_SHAPES[i][1],
             "prim": True}
            for i, n in SYMBOLS
        ],
    )
    run(
        "INSERT INTO formula (id, formula_type_id, hash, token_count, created_at) "
        f"VALUES (:id, {PROPOSITION_TYPE}, :hash, :count, :now)",
        [{"id": f, "hash": f"ci-old-{f}", "count": len(t)} for f, t in FORMULAS.items()],
    )
    token_rows = []
    for formula_id, tokens in FORMULAS.items():
        for position, token in enumerate(tokens):
            bound = isinstance(token, tuple)
            token_rows.append(
                {
                    "id": len(token_rows) + 1,
                    "formula_id": formula_id,
                    "position": position,
                    "symbol_id": None if bound else token,
                    "bound": token[1] if bound else None,
                }
            )
    run(
        "INSERT INTO formula_token (id, formula_id, position, symbol_id, de_bruijn_index) "
        "VALUES (:id, :formula_id, :position, :symbol_id, :bound)",
        token_rows,
    )
    run(
        "INSERT INTO definition (id, name, kind, new_symbol_id, requires_existence_proof, "
        "requires_uniqueness_proof, created_at) "
        "VALUES (1, 'def_and', 'logical', 4, :no, :no, :now)",
        [{"no": False}],
    )
    run(
        "INSERT INTO axiom (id, name, formula_id, origin_kind, created_at) "
        "VALUES (:id, :name, :formula_id, 'primitive', :now)",
        [{"id": 2, "name": "ax_b", "formula_id": 2}, {"id": 1, "name": "ax_a", "formula_id": 1}],
    )
    run(
        "INSERT INTO theorem (id, name, conclusion_formula_id, status, created_at, updated_at) "
        "VALUES (:id, :name, :formula_id, 'proven', :now, :now)",
        [{"id": i, "name": n, "formula_id": f} for i, n, f in THEOREMS],
    )
    run(
        "INSERT INTO proof (id, theorem_id, status, created_at, updated_at) "
        "VALUES (:id, :theorem_id, 'verified', :now, :now)",
        [{"id": p, "theorem_id": t} for p, t in PROOFS],
    )


def _expected_hash(tokens, symbol_key) -> str:
    return hashlib.sha256(
        "".join(
            f"B{t[1]};" if isinstance(t, tuple) else f"S{symbol_key[t]};" for t in tokens
        ).encode()
    ).hexdigest()


def _scalars(connection, sql):
    return connection.execute(sa.text(sql)).all()


def check_head(connection) -> None:
    ns = DEFAULT_NAMESPACE_NAME
    assert _scalars(connection, "SELECT id, name, parent_id FROM namespace ORDER BY id") == [
        (1, "dem.foundation", None),
        (2, ns, 1),
    ]
    symbol_public = {
        i: deterministic_public_id("symbol", f"{ns}::{n}") for i, n in SYMBOLS
    }
    assert dict(_scalars(connection, "SELECT id, public_id FROM symbol")) == symbol_public
    assert {r[0] for r in _scalars(connection, "SELECT namespace_id FROM symbol")} == {2}

    hashes = {f: _expected_hash(t, symbol_public) for f, t in FORMULAS.items()}
    assert len(set(hashes.values())) == len(FORMULAS)
    assert dict(_scalars(connection, "SELECT id, hash FROM formula")) == hashes
    assert dict(_scalars(connection, "SELECT id, public_id FROM formula")) == {
        f: deterministic_public_id("formula", h) for f, h in hashes.items()
    }
    assert dict(_scalars(connection, "SELECT id, public_id FROM axiom")) == {
        1: deterministic_public_id("axiom", f"{ns}::ax_a"),
        2: deterministic_public_id("axiom", f"{ns}::ax_b"),
    }
    assert dict(_scalars(connection, "SELECT id, public_id FROM definition")) == {
        1: deterministic_public_id("definition", f"{ns}::def_and")
    }
    theorem_public = {
        i: deterministic_public_id("theorem", f"{ns}::{n}") for i, n, _ in THEOREMS
    }
    assert dict(_scalars(connection, "SELECT id, public_id FROM theorem")) == theorem_public

    expected_proofs, next_ordinal = {}, {}
    for proof_id, theorem_id in sorted(PROOFS, key=lambda row: (row[1], row[0])):
        ordinal = next_ordinal.get(theorem_id, 0)
        expected_proofs[proof_id] = (
            deterministic_public_id("proof", f"{theorem_public[theorem_id]}::{ordinal}"),
            ordinal,
        )
        next_ordinal[theorem_id] = ordinal + 1
    assert {
        r[0]: (r[1], r[2])
        for r in _scalars(connection, "SELECT id, public_id, identity_ordinal FROM proof")
    } == expected_proofs
    assert dict(
        _scalars(connection, "SELECT theorem_id, next_ordinal FROM proof_identity_sequence")
    ) == next_ordinal

    for table in ("symbol", "formula", "axiom", "definition", "theorem", "proof"):
        for (value,) in _scalars(connection, f"SELECT public_id FROM {table}"):
            assert str(UUID(value)) == value, (table, value)

    # The migration inserts namespaces with explicit ids; a later insert without
    # an id (as dem.identity.ensure_namespace does) must not collide with them.
    connection.execute(
        sa.text("INSERT INTO namespace (name, parent_id) VALUES ('ci.extra', 2)")
    )
    assert _scalars(connection, "SELECT id FROM namespace WHERE name = 'ci.extra'") == [(3,)]
    connection.execute(sa.text("DELETE FROM namespace WHERE name = 'ci.extra'"))


def check_base(connection) -> None:
    inspector = sa.inspect(connection)
    assert "namespace" not in inspector.get_table_names()
    assert "proof_identity_sequence" not in inspector.get_table_names()
    for table in ("symbol", "formula", "axiom", "definition", "theorem", "proof"):
        assert "public_id" not in {c["name"] for c in inspector.get_columns(table)}, table
    # downgrade() restores hashes keyed by symbol id instead of public id.
    assert dict(_scalars(connection, "SELECT id, hash FROM formula")) == {
        f: _expected_hash(t, {i: i for i, _ in SYMBOLS}) for f, t in FORMULAS.items()
    }
    assert {r[0] for r in _scalars(connection, "SELECT namespace_id FROM symbol")} == {2}


def main() -> None:
    action = {"seed": seed, "check-head": check_head, "check-base": check_base}[sys.argv[1]]
    engine = sa.create_engine(os.environ["DEM_DATABASE_URL"])
    with engine.begin() as connection:
        action(connection)
    engine.dispose()
    print(f"{sys.argv[1]}: ok ({engine.dialect.name})")


if __name__ == "__main__":
    main()
