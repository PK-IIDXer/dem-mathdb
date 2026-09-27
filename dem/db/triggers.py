"""Database triggers that enforce Tier A and Tier B kernel invariants.

The definitions in this module are shared by Alembic and SQLAlchemy's
``MetaData.create_all()`` path.  Keep the trigger names and event layout stable:
the two schema origins are compared in ``tests/test_alembic_history.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Connection, event, text
from sqlalchemy.schema import MetaData


@dataclass(frozen=True)
class TriggerSpec:
    name: str
    table: str
    event: str


_PROOF_CONTENT_TABLES = (
    "proof_step",
    "proof_step_arg",
    "proof_step_subst_term",
    "proof_step_subst_prop",
    "proof_step_subst_prop_param",
)

FOUNDATIONAL_TIER_A_TRIGGER_SPECS = (
    TriggerSpec("theorem_conclusion_immutable_update", "theorem", "UPDATE"),
    TriggerSpec("theorem_no_delete_proven", "theorem", "DELETE"),
    TriggerSpec("theorem_premise_no_late_insert", "theorem_premise", "INSERT"),
    TriggerSpec("theorem_premise_immutable_update", "theorem_premise", "UPDATE"),
    TriggerSpec("theorem_premise_immutable_delete", "theorem_premise", "DELETE"),
    TriggerSpec("proof_status_monotonic_update", "proof", "UPDATE"),
    TriggerSpec("proof_no_delete_verified", "proof", "DELETE"),
    *(
        TriggerSpec(f"{table}_{event.lower()}_draft_only", table, event)
        for table in _PROOF_CONTENT_TABLES
        for event in ("INSERT", "UPDATE", "DELETE")
    ),
)

TIER_A_EXTENSION_TRIGGER_SPECS = (
    TriggerSpec("axiom_formula_immutable_update", "axiom", "UPDATE"),
    TriggerSpec("proof_theorem_immutable_update", "proof", "UPDATE"),
)

# N11-C (lean-import-design §3.7, D7): a theorem becomes proven only through a
# verified proof, and a proof starts as a draft.  ProofService.validate() is the
# only writer of 'verified' and flushes the proof before promoting its theorem.
PROVEN_REQUIRES_VERIFIED_TRIGGER_SPECS = (
    TriggerSpec("theorem_proven_requires_verified_insert", "theorem", "INSERT"),
    TriggerSpec("theorem_proven_requires_verified_update", "theorem", "UPDATE"),
    TriggerSpec("proof_insert_draft_only", "proof", "INSERT"),
)

TIER_A_TRIGGER_SPECS = (
    *FOUNDATIONAL_TIER_A_TRIGGER_SPECS,
    *TIER_A_EXTENSION_TRIGGER_SPECS,
    *PROVEN_REQUIRES_VERIFIED_TRIGGER_SPECS,
)

PROVEN_WITHOUT_VERIFIED_PROOF_SQL = """
SELECT theorem.id
FROM theorem
WHERE theorem.status = 'proven'
  AND NOT EXISTS (
      SELECT 1 FROM proof
      WHERE proof.theorem_id = theorem.id AND proof.status = 'verified'
  )
ORDER BY theorem.id
"""

SQLITE_TIER_B_TRIGGER_SPECS = (
    TriggerSpec(
        "formula_wellformed_after_insert", "formula_token", "INSERT"
    ),
)

POSTGRES_TIER_B_TRIGGER_SPECS = (
    TriggerSpec(
        "formula_wellformed_deferred_insert", "formula", "INSERT"
    ),
)

TIER_B_IMMUTABILITY_TRIGGER_SPECS = (
    TriggerSpec("formula_identity_immutable_update", "formula", "UPDATE"),
    TriggerSpec("formula_no_delete_completed", "formula", "DELETE"),
    TriggerSpec(
        "formula_token_insert_incomplete_only", "formula_token", "INSERT"
    ),
    TriggerSpec(
        "formula_token_update_incomplete_only", "formula_token", "UPDATE"
    ),
    TriggerSpec(
        "formula_token_delete_incomplete_only", "formula_token", "DELETE"
    ),
    TriggerSpec("symbol_identity_immutable_update", "symbol", "UPDATE"),
    TriggerSpec(
        "formula_type_semantics_immutable_update", "formula_type", "UPDATE"
    ),
    TriggerSpec(
        "symbol_type_semantics_immutable_update", "symbol_type", "UPDATE"
    ),
)

INCOMPLETE_FORMULAS_SQL = """
SELECT formula.id,
       formula.token_count,
       COUNT(formula_token.id) AS actual_token_count
FROM formula
LEFT JOIN formula_token ON formula_token.formula_id = formula.id
GROUP BY formula.id, formula.token_count
HAVING COUNT(formula_token.id) <> formula.token_count
ORDER BY formula.id
"""


_SQLITE_GUARDS = {
    "axiom_formula_immutable_update": (
        "NEW.formula_id IS NOT OLD.formula_id",
        "axiom formula is immutable",
    ),
    "theorem_conclusion_immutable_update": (
        "NEW.conclusion_formula_id IS NOT OLD.conclusion_formula_id",
        "theorem conclusion is immutable",
    ),
    "theorem_no_delete_proven": (
        "OLD.status = 'proven'",
        "a proven theorem cannot be deleted",
    ),
    "theorem_premise_no_late_insert": (
        "EXISTS (SELECT 1 FROM proof "
        "WHERE theorem_id = NEW.theorem_id AND status = 'verified')",
        "cannot add a premise to a theorem with a verified proof",
    ),
    "theorem_premise_immutable_update": (
        "1",
        "theorem premises are immutable",
    ),
    "theorem_premise_immutable_delete": (
        "EXISTS (SELECT 1 FROM theorem WHERE id = OLD.theorem_id)",
        "theorem premises are immutable",
    ),
    "proof_status_monotonic_update": (
        "OLD.status = 'verified' AND NEW.status <> 'verified'",
        "a verified proof cannot be demoted",
    ),
    "proof_theorem_immutable_update": (
        "OLD.status = 'verified' AND NEW.theorem_id IS NOT OLD.theorem_id",
        "a verified proof cannot change theorem",
    ),
    "proof_no_delete_verified": (
        "OLD.status = 'verified'",
        "a verified proof cannot be deleted",
    ),
    "theorem_proven_requires_verified_insert": (
        "NEW.status = 'proven' AND NOT EXISTS (SELECT 1 FROM proof "
        "WHERE theorem_id = NEW.id AND status = 'verified')",
        "a theorem can only be proven by a verified proof",
    ),
    "theorem_proven_requires_verified_update": (
        "NEW.status = 'proven' AND NOT EXISTS (SELECT 1 FROM proof "
        "WHERE theorem_id = NEW.id AND status = 'verified')",
        "a theorem can only be proven by a verified proof",
    ),
    "proof_insert_draft_only": (
        "NEW.status IS NOT 'draft'",
        "a proof must be created as a draft",
    ),
}


def _sqlite_guard(spec: TriggerSpec) -> tuple[str, str]:
    fixed = _SQLITE_GUARDS.get(spec.name)
    if fixed is not None:
        return fixed
    if spec.event == "INSERT":
        condition = (
            "NOT EXISTS (SELECT 1 FROM proof "
            "WHERE id = NEW.proof_id AND status = 'draft')"
        )
    elif spec.event == "UPDATE":
        condition = (
            "NOT EXISTS (SELECT 1 FROM proof "
            "WHERE id = OLD.proof_id AND status = 'draft') "
            "OR NOT EXISTS (SELECT 1 FROM proof "
            "WHERE id = NEW.proof_id AND status = 'draft')"
        )
    else:
        condition = (
            "EXISTS (SELECT 1 FROM proof "
            "WHERE id = OLD.proof_id AND status <> 'draft')"
        )
    return condition, "proof content may only be edited while the proof is draft"


_POSTGRES_FUNCTION = """
CREATE OR REPLACE FUNCTION dem_tier_a_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_NAME = 'axiom_formula_immutable_update' THEN
        IF NEW.formula_id IS DISTINCT FROM OLD.formula_id THEN
            RAISE EXCEPTION 'axiom formula is immutable' USING ERRCODE = '23514';
        END IF;
    ELSIF TG_NAME = 'theorem_conclusion_immutable_update' THEN
        IF NEW.conclusion_formula_id IS DISTINCT FROM OLD.conclusion_formula_id THEN
            RAISE EXCEPTION 'theorem conclusion is immutable' USING ERRCODE = '23514';
        END IF;
    ELSIF TG_NAME = 'theorem_no_delete_proven' THEN
        IF OLD.status = 'proven' THEN
            RAISE EXCEPTION 'a proven theorem cannot be deleted' USING ERRCODE = '23514';
        END IF;
    ELSIF TG_NAME = 'theorem_premise_no_late_insert' THEN
        IF EXISTS (
            SELECT 1 FROM proof
            WHERE theorem_id = NEW.theorem_id AND status = 'verified'
        ) THEN
            RAISE EXCEPTION 'cannot add a premise to a theorem with a verified proof'
                USING ERRCODE = '23514';
        END IF;
    ELSIF TG_NAME = 'theorem_premise_immutable_update' THEN
        RAISE EXCEPTION 'theorem premises are immutable' USING ERRCODE = '23514';
    ELSIF TG_NAME = 'theorem_premise_immutable_delete' THEN
        IF EXISTS (SELECT 1 FROM theorem WHERE id = OLD.theorem_id) THEN
            RAISE EXCEPTION 'theorem premises are immutable' USING ERRCODE = '23514';
        END IF;
    ELSIF TG_NAME = 'proof_status_monotonic_update' THEN
        IF OLD.status = 'verified' AND NEW.status <> 'verified' THEN
            RAISE EXCEPTION 'a verified proof cannot be demoted' USING ERRCODE = '23514';
        END IF;
    ELSIF TG_NAME = 'proof_theorem_immutable_update' THEN
        IF OLD.status = 'verified' AND NEW.theorem_id IS DISTINCT FROM OLD.theorem_id THEN
            RAISE EXCEPTION 'a verified proof cannot change theorem'
                USING ERRCODE = '23514';
        END IF;
    ELSIF TG_NAME = 'proof_no_delete_verified' THEN
        IF OLD.status = 'verified' THEN
            RAISE EXCEPTION 'a verified proof cannot be deleted' USING ERRCODE = '23514';
        END IF;
    ELSIF TG_NAME IN (
        'theorem_proven_requires_verified_insert',
        'theorem_proven_requires_verified_update'
    ) THEN
        IF NEW.status = 'proven' AND NOT EXISTS (
            SELECT 1 FROM proof WHERE theorem_id = NEW.id AND status = 'verified'
        ) THEN
            RAISE EXCEPTION 'a theorem can only be proven by a verified proof'
                USING ERRCODE = '23514';
        END IF;
    ELSIF TG_NAME = 'proof_insert_draft_only' THEN
        IF NEW.status IS DISTINCT FROM 'draft' THEN
            RAISE EXCEPTION 'a proof must be created as a draft' USING ERRCODE = '23514';
        END IF;
    ELSIF TG_TABLE_NAME IN (
        'proof_step',
        'proof_step_arg',
        'proof_step_subst_term',
        'proof_step_subst_prop',
        'proof_step_subst_prop_param'
    ) THEN
        IF TG_OP = 'INSERT' THEN
            IF NOT EXISTS (
                SELECT 1 FROM proof WHERE id = NEW.proof_id AND status = 'draft'
            ) THEN
                RAISE EXCEPTION 'proof content may only be edited while the proof is draft'
                    USING ERRCODE = '23514';
            END IF;
        ELSIF TG_OP = 'UPDATE' THEN
            IF NOT EXISTS (
                SELECT 1 FROM proof WHERE id = OLD.proof_id AND status = 'draft'
            ) OR NOT EXISTS (
                SELECT 1 FROM proof WHERE id = NEW.proof_id AND status = 'draft'
            ) THEN
                RAISE EXCEPTION 'proof content may only be edited while the proof is draft'
                    USING ERRCODE = '23514';
            END IF;
        ELSIF EXISTS (
            SELECT 1 FROM proof WHERE id = OLD.proof_id AND status <> 'draft'
        ) THEN
            RAISE EXCEPTION 'proof content may only be edited while the proof is draft'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$
"""


def _sqlite_formula_check_sql(formula_id_expression: str) -> str:
    """Return the single-formula Tier B checker used by tests and the trigger."""
    return f"""
    WITH RECURSIVE
    meta(symbol_id, arity, is_quantifier, out_code, in_code) AS (
        SELECT symbol.id,
               symbol.arity,
               symbol_type.is_quantifier,
               CASE output_type.code
                   WHEN 'term' THEN 'T'
                   WHEN 'proposition' THEN 'P'
               END,
               CASE input_type.code
                   WHEN 'term' THEN 'T'
                   WHEN 'proposition' THEN 'P'
               END
        FROM symbol
        JOIN symbol_type ON symbol_type.id = symbol.symbol_type_id
        JOIN formula_type AS output_type
          ON output_type.id = symbol_type.output_formula_type_id
        LEFT JOIN formula_type AS input_type
          ON input_type.id = symbol_type.input_formula_type_id
    ),
    walk(pos, stack, root_code, error) AS (
        SELECT 0, 'A0,', NULL, NULL
        UNION ALL
        SELECT
            walk.pos + 1,
            CASE
                WHEN token.symbol_id IS NULL THEN
                    substr(walk.stack, instr(walk.stack, ',') + 1)
                WHEN meta.is_quantifier = 1 THEN
                    'P' ||
                    (CAST(substr(
                        walk.stack,
                        2,
                        instr(walk.stack, ',') - 2
                    ) AS INTEGER) + 1) || ',' ||
                    substr(walk.stack, instr(walk.stack, ',') + 1)
                ELSE
                    replace(
                        hex(zeroblob(meta.arity)),
                        '00',
                        coalesce(meta.in_code, '!') ||
                        substr(
                            walk.stack,
                            2,
                            instr(walk.stack, ',') - 2
                        ) || ','
                    ) || substr(walk.stack, instr(walk.stack, ',') + 1)
            END,
            CASE
                WHEN walk.pos = 0 THEN
                    CASE
                        WHEN token.symbol_id IS NULL THEN 'T'
                        ELSE meta.out_code
                    END
                ELSE walk.root_code
            END,
            CASE
                WHEN token.symbol_id IS NULL THEN
                    CASE
                        WHEN substr(walk.stack, 1, 1) NOT IN ('A', 'T')
                            THEN 'type-mismatch'
                        WHEN token.de_bruijn_index >= CAST(substr(
                            walk.stack,
                            2,
                            instr(walk.stack, ',') - 2
                        ) AS INTEGER)
                            THEN 'unbound-de-bruijn'
                    END
                WHEN meta.symbol_id IS NULL THEN 'unknown-symbol'
                WHEN substr(walk.stack, 1, 1) <> 'A'
                     AND substr(walk.stack, 1, 1) <> meta.out_code
                    THEN 'type-mismatch'
                WHEN meta.is_quantifier = 1 AND meta.arity <> 1
                    THEN 'quantifier-arity'
                WHEN meta.is_quantifier = 0
                     AND meta.arity > 0
                     AND meta.in_code IS NULL
                    THEN 'symbol-takes-no-args'
            END
        FROM walk
        JOIN formula_token AS token
          ON token.formula_id = {formula_id_expression}
         AND token.position = walk.pos
        LEFT JOIN meta ON meta.symbol_id = token.symbol_id
        WHERE walk.error IS NULL AND walk.stack <> ''
    ),
    last AS (
        SELECT pos, stack, root_code, error
        FROM walk
        ORDER BY pos DESC
        LIMIT 1
    )
    SELECT
        CASE
            WHEN last.error IS NOT NULL THEN last.error
            WHEN last.stack <> '' THEN 'unexpected-end'
            WHEN last.pos < formula.token_count THEN 'trailing-tokens'
            WHEN last.root_code <> CASE formula_type.code
                WHEN 'term' THEN 'T'
                WHEN 'proposition' THEN 'P'
            END THEN 'root-type-mismatch'
            ELSE 'ok'
        END AS verdict
    FROM formula
    JOIN formula_type ON formula_type.id = formula.formula_type_id
    CROSS JOIN last
    WHERE formula.id = {formula_id_expression}
    """


_POSTGRES_FORMULA_FUNCTION = """
CREATE OR REPLACE FUNCTION dem_formula_wellformed(checked_formula_id integer)
RETURNS boolean
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    expected_stack text := 'A0,';
    expected_code text;
    expected_depth integer;
    separator_position integer;
    root_code text := NULL;
    stored_code text;
    expected_token_count integer;
    consumed integer := 0;
    token_row record;
    symbol_arity integer;
    symbol_is_quantifier boolean;
    symbol_out_code text;
    symbol_in_code text;
BEGIN
    SELECT formula.token_count, formula_type.code
      INTO expected_token_count, stored_code
      FROM formula
      JOIN formula_type ON formula_type.id = formula.formula_type_id
     WHERE formula.id = checked_formula_id;
    IF NOT FOUND THEN
        RETURN false;
    END IF;

    FOR token_row IN
        SELECT position, symbol_id, de_bruijn_index
          FROM formula_token
         WHERE formula_id = checked_formula_id
         ORDER BY position
    LOOP
        IF token_row.position <> consumed OR expected_stack = '' THEN
            RETURN false;
        END IF;

        separator_position := position(',' IN expected_stack);
        IF separator_position = 0 THEN
            RETURN false;
        END IF;
        expected_code := substr(expected_stack, 1, 1);
        expected_depth := substr(
            expected_stack, 2, separator_position - 2
        )::integer;
        expected_stack := substr(expected_stack, separator_position + 1);

        IF token_row.symbol_id IS NULL THEN
            IF expected_code NOT IN ('A', 'T')
               OR token_row.de_bruijn_index >= expected_depth THEN
                RETURN false;
            END IF;
            IF consumed = 0 THEN
                root_code := 'T';
            END IF;
        ELSE
            SELECT symbol.arity,
                   symbol_type.is_quantifier,
                   CASE output_type.code
                       WHEN 'term' THEN 'T'
                       WHEN 'proposition' THEN 'P'
                   END,
                   CASE input_type.code
                       WHEN 'term' THEN 'T'
                       WHEN 'proposition' THEN 'P'
                   END
              INTO symbol_arity,
                   symbol_is_quantifier,
                   symbol_out_code,
                   symbol_in_code
              FROM symbol
              JOIN symbol_type ON symbol_type.id = symbol.symbol_type_id
              JOIN formula_type AS output_type
                ON output_type.id = symbol_type.output_formula_type_id
              LEFT JOIN formula_type AS input_type
                ON input_type.id = symbol_type.input_formula_type_id
             WHERE symbol.id = token_row.symbol_id;
            IF NOT FOUND OR symbol_out_code IS NULL THEN
                RETURN false;
            END IF;
            IF expected_code <> 'A' AND expected_code <> symbol_out_code THEN
                RETURN false;
            END IF;
            IF consumed = 0 THEN
                root_code := symbol_out_code;
            END IF;

            IF symbol_is_quantifier THEN
                IF symbol_arity <> 1 THEN
                    RETURN false;
                END IF;
                expected_stack :=
                    'P' || (expected_depth + 1)::text || ',' || expected_stack;
            ELSE
                IF symbol_arity > 0 AND symbol_in_code IS NULL THEN
                    RETURN false;
                END IF;
                expected_stack := repeat(
                    coalesce(symbol_in_code, '!') || expected_depth::text || ',',
                    symbol_arity
                ) || expected_stack;
            END IF;
        END IF;
        consumed := consumed + 1;
    END LOOP;

    RETURN consumed = expected_token_count
       AND expected_stack = ''
       AND root_code = CASE stored_code
           WHEN 'term' THEN 'T'
           WHEN 'proposition' THEN 'P'
       END;
END;
$$;

CREATE OR REPLACE FUNCTION dem_formula_wellformed_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NOT dem_formula_wellformed(NEW.id) THEN
        RAISE EXCEPTION 'formula is not well-formed' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
"""


def formula_is_wellformed(connection: Connection, formula_id: int) -> bool:
    """Run the database-side Tier B decision for one existing formula."""
    if connection.dialect.name == "sqlite":
        verdict = connection.scalar(
            text(_sqlite_formula_check_sql(":formula_id")),
            {"formula_id": formula_id},
        )
        return verdict == "ok"
    if connection.dialect.name == "postgresql":
        return bool(
            connection.scalar(
                text("SELECT dem_formula_wellformed(:formula_id)"),
                {"formula_id": formula_id},
            )
        )
    raise RuntimeError(
        f"Tier B formula checks do not support dialect {connection.dialect.name!r}"
    )


def incomplete_formulas(connection: Connection) -> list[tuple[int, int, int]]:
    """List formulas whose stored token count differs from their actual rows."""
    return [tuple(row) for row in connection.execute(text(INCOMPLETE_FORMULAS_SQL))]


def _validate_existing_formulas(connection: Connection) -> None:
    for formula_id in connection.scalars(text("SELECT id FROM formula ORDER BY id")):
        if not formula_is_wellformed(connection, formula_id):
            raise RuntimeError(
                f"cannot install Tier B gate: formula {formula_id} is not well-formed"
            )


def create_tier_b_wellformed_gate(connection: Connection) -> None:
    """Install the Tier B well-formedness gate for the current dialect."""
    dialect = connection.dialect.name
    if dialect == "sqlite":
        _validate_existing_formulas(connection)
        check_sql = _sqlite_formula_check_sql("NEW.formula_id")
        connection.exec_driver_sql(
            f"""
            CREATE TRIGGER IF NOT EXISTS formula_wellformed_after_insert
            AFTER INSERT ON formula_token
            FOR EACH ROW
            WHEN (
                SELECT COUNT(*) FROM formula_token
                WHERE formula_id = NEW.formula_id
            ) = (
                SELECT token_count FROM formula WHERE id = NEW.formula_id
            )
            BEGIN
                SELECT RAISE(ABORT, 'formula is not well-formed')
                FROM ({check_sql}) AS formula_check
                WHERE formula_check.verdict <> 'ok';
            END
            """
        )
        return
    if dialect == "postgresql":
        connection.exec_driver_sql(_POSTGRES_FORMULA_FUNCTION)
        _validate_existing_formulas(connection)
        connection.exec_driver_sql(
            """
            DO $dem_trigger$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_trigger
                    WHERE tgname = 'formula_wellformed_deferred_insert'
                      AND tgrelid = 'formula'::regclass
                      AND NOT tgisinternal
                ) THEN
                    CREATE CONSTRAINT TRIGGER formula_wellformed_deferred_insert
                    AFTER INSERT ON formula
                    DEFERRABLE INITIALLY DEFERRED
                    FOR EACH ROW EXECUTE FUNCTION dem_formula_wellformed_guard();
                END IF;
            END
            $dem_trigger$
            """
        )
        return
    raise RuntimeError(f"Tier B triggers do not support dialect {dialect!r}")


def drop_tier_b_wellformed_gate(connection: Connection) -> None:
    """Remove the Tier B well-formedness gate during an Alembic downgrade."""
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql(
            "DROP TRIGGER IF EXISTS formula_wellformed_after_insert"
        )
        return
    if connection.dialect.name == "postgresql":
        connection.exec_driver_sql(
            "DROP TRIGGER IF EXISTS formula_wellformed_deferred_insert ON formula"
        )
        connection.exec_driver_sql(
            "DROP FUNCTION IF EXISTS dem_formula_wellformed_guard()"
        )
        connection.exec_driver_sql(
            "DROP FUNCTION IF EXISTS dem_formula_wellformed(integer)"
        )
        return
    raise RuntimeError(
        f"Tier B triggers do not support dialect {connection.dialect.name!r}"
    )


_SQLITE_TIER_B_IMMUTABILITY_GUARDS = {
    "formula_identity_immutable_update": (
        "NEW.public_id IS NOT OLD.public_id "
        "OR NEW.formula_type_id IS NOT OLD.formula_type_id "
        "OR NEW.hash IS NOT OLD.hash "
        "OR NEW.token_count IS NOT OLD.token_count "
        "OR NEW.created_at IS NOT OLD.created_at",
        "formula identity is immutable",
    ),
    "formula_no_delete_completed": (
        "(SELECT COUNT(*) FROM formula_token WHERE formula_id = OLD.id) "
        ">= OLD.token_count",
        "a completed formula cannot be deleted",
    ),
    "formula_token_insert_incomplete_only": (
        "EXISTS ("
        "SELECT 1 FROM formula WHERE id = NEW.formula_id "
        "AND (SELECT COUNT(*) FROM formula_token "
        "WHERE formula_id = NEW.formula_id) >= token_count"
        ")",
        "completed formula tokens are immutable",
    ),
    "formula_token_update_incomplete_only": (
        "NEW.formula_id IS NOT OLD.formula_id OR EXISTS ("
        "SELECT 1 FROM formula WHERE id = OLD.formula_id "
        "AND (SELECT COUNT(*) FROM formula_token "
        "WHERE formula_id = OLD.formula_id) >= token_count"
        ")",
        "completed formula tokens are immutable",
    ),
    "formula_token_delete_incomplete_only": (
        "EXISTS ("
        "SELECT 1 FROM formula WHERE id = OLD.formula_id "
        "AND (SELECT COUNT(*) FROM formula_token "
        "WHERE formula_id = OLD.formula_id) >= token_count"
        ")",
        "completed formula tokens are immutable",
    ),
    "symbol_identity_immutable_update": (
        "NEW.public_id IS NOT OLD.public_id "
        "OR NEW.symbol_type_id IS NOT OLD.symbol_type_id "
        "OR NEW.arity IS NOT OLD.arity",
        "symbol identity and shape are immutable",
    ),
    "formula_type_semantics_immutable_update": (
        "NEW.name IS NOT OLD.name OR NEW.code IS NOT OLD.code",
        "formula type semantics are immutable",
    ),
    "symbol_type_semantics_immutable_update": (
        "NEW.name IS NOT OLD.name "
        "OR NEW.output_formula_type_id IS NOT OLD.output_formula_type_id "
        "OR NEW.input_formula_type_id IS NOT OLD.input_formula_type_id "
        "OR NEW.fixed_arity IS NOT OLD.fixed_arity "
        "OR NEW.is_quantifier IS NOT OLD.is_quantifier",
        "symbol type semantics are immutable",
    ),
}


_POSTGRES_TIER_B_IMMUTABILITY_FUNCTION = """
CREATE OR REPLACE FUNCTION dem_tier_b_immutability_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_NAME = 'formula_identity_immutable_update' THEN
        IF NEW.public_id IS DISTINCT FROM OLD.public_id
           OR NEW.formula_type_id IS DISTINCT FROM OLD.formula_type_id
           OR NEW.hash IS DISTINCT FROM OLD.hash
           OR NEW.token_count IS DISTINCT FROM OLD.token_count
           OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION 'formula identity is immutable' USING ERRCODE = '23514';
        END IF;
    ELSIF TG_NAME = 'formula_no_delete_completed' THEN
        IF (
            SELECT COUNT(*) FROM formula_token WHERE formula_id = OLD.id
        ) >= OLD.token_count THEN
            RAISE EXCEPTION 'a completed formula cannot be deleted'
                USING ERRCODE = '23514';
        END IF;
    ELSIF TG_NAME = 'formula_token_insert_incomplete_only' THEN
        IF EXISTS (
            SELECT 1 FROM formula
            WHERE id = NEW.formula_id
              AND (
                  SELECT COUNT(*) FROM formula_token
                  WHERE formula_id = NEW.formula_id
              ) >= token_count
        ) THEN
            RAISE EXCEPTION 'completed formula tokens are immutable'
                USING ERRCODE = '23514';
        END IF;
    ELSIF TG_NAME = 'formula_token_update_incomplete_only' THEN
        IF NEW.formula_id IS DISTINCT FROM OLD.formula_id OR EXISTS (
            SELECT 1 FROM formula
            WHERE id = OLD.formula_id
              AND (
                  SELECT COUNT(*) FROM formula_token
                  WHERE formula_id = OLD.formula_id
              ) >= token_count
        ) THEN
            RAISE EXCEPTION 'completed formula tokens are immutable'
                USING ERRCODE = '23514';
        END IF;
    ELSIF TG_NAME = 'formula_token_delete_incomplete_only' THEN
        IF EXISTS (
            SELECT 1 FROM formula
            WHERE id = OLD.formula_id
              AND (
                  SELECT COUNT(*) FROM formula_token
                  WHERE formula_id = OLD.formula_id
              ) >= token_count
        ) THEN
            RAISE EXCEPTION 'completed formula tokens are immutable'
                USING ERRCODE = '23514';
        END IF;
    ELSIF TG_NAME = 'symbol_identity_immutable_update' THEN
        IF NEW.public_id IS DISTINCT FROM OLD.public_id
           OR NEW.symbol_type_id IS DISTINCT FROM OLD.symbol_type_id
           OR NEW.arity IS DISTINCT FROM OLD.arity THEN
            RAISE EXCEPTION 'symbol identity and shape are immutable'
                USING ERRCODE = '23514';
        END IF;
    ELSIF TG_NAME = 'formula_type_semantics_immutable_update' THEN
        IF NEW.name IS DISTINCT FROM OLD.name
           OR NEW.code IS DISTINCT FROM OLD.code THEN
            RAISE EXCEPTION 'formula type semantics are immutable'
                USING ERRCODE = '23514';
        END IF;
    ELSIF TG_NAME = 'symbol_type_semantics_immutable_update' THEN
        IF NEW.name IS DISTINCT FROM OLD.name
           OR NEW.output_formula_type_id IS DISTINCT FROM OLD.output_formula_type_id
           OR NEW.input_formula_type_id IS DISTINCT FROM OLD.input_formula_type_id
           OR NEW.fixed_arity IS DISTINCT FROM OLD.fixed_arity
           OR NEW.is_quantifier IS DISTINCT FROM OLD.is_quantifier THEN
            RAISE EXCEPTION 'symbol type semantics are immutable'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$
"""


def create_tier_b_immutability_triggers(connection: Connection) -> None:
    """Install guards that keep accepted formulas and symbol shapes stable."""
    dialect = connection.dialect.name
    if dialect == "sqlite":
        for spec in TIER_B_IMMUTABILITY_TRIGGER_SPECS:
            condition, message = _SQLITE_TIER_B_IMMUTABILITY_GUARDS[spec.name]
            connection.exec_driver_sql(
                f"""
                CREATE TRIGGER IF NOT EXISTS {spec.name}
                BEFORE {spec.event} ON {spec.table}
                FOR EACH ROW WHEN {condition}
                BEGIN
                    SELECT RAISE(ABORT, '{message}');
                END
                """
            )
        return
    if dialect == "postgresql":
        connection.exec_driver_sql(_POSTGRES_TIER_B_IMMUTABILITY_FUNCTION)
        for spec in TIER_B_IMMUTABILITY_TRIGGER_SPECS:
            connection.exec_driver_sql(
                f"""
                DO $dem_trigger$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_trigger
                        WHERE tgname = '{spec.name}'
                          AND tgrelid = '{spec.table}'::regclass
                          AND NOT tgisinternal
                    ) THEN
                        CREATE TRIGGER {spec.name}
                        BEFORE {spec.event} ON {spec.table}
                        FOR EACH ROW
                        EXECUTE FUNCTION dem_tier_b_immutability_guard();
                    END IF;
                END
                $dem_trigger$
                """
            )
        return
    raise RuntimeError(
        f"Tier B immutability triggers do not support dialect {dialect!r}"
    )


def drop_tier_b_immutability_triggers(connection: Connection) -> None:
    """Remove all Tier B immutability guards during a downgrade."""
    dialect = connection.dialect.name
    if dialect == "sqlite":
        for spec in reversed(TIER_B_IMMUTABILITY_TRIGGER_SPECS):
            connection.exec_driver_sql(f"DROP TRIGGER IF EXISTS {spec.name}")
        return
    if dialect == "postgresql":
        for spec in reversed(TIER_B_IMMUTABILITY_TRIGGER_SPECS):
            connection.exec_driver_sql(
                f"DROP TRIGGER IF EXISTS {spec.name} ON {spec.table}"
            )
        connection.exec_driver_sql(
            "DROP FUNCTION IF EXISTS dem_tier_b_immutability_guard()"
        )
        return
    raise RuntimeError(
        f"Tier B immutability triggers do not support dialect {dialect!r}"
    )


def create_tier_a_triggers(
    connection: Connection,
    specs: tuple[TriggerSpec, ...] = TIER_A_TRIGGER_SPECS,
) -> None:
    """Install the Tier A guards for the connection's SQL dialect."""
    dialect = connection.dialect.name
    if dialect == "sqlite":
        for spec in specs:
            condition, message = _sqlite_guard(spec)
            connection.exec_driver_sql(
                f"""
                CREATE TRIGGER IF NOT EXISTS {spec.name}
                BEFORE {spec.event} ON {spec.table}
                FOR EACH ROW WHEN {condition}
                BEGIN
                    SELECT RAISE(ABORT, '{message}');
                END
                """
            )
        return
    if dialect == "postgresql":
        connection.exec_driver_sql(_POSTGRES_FUNCTION)
        for spec in specs:
            connection.exec_driver_sql(
                f"""
                DO $dem_trigger$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_trigger
                        WHERE tgname = '{spec.name}'
                          AND tgrelid = '{spec.table}'::regclass
                          AND NOT tgisinternal
                    ) THEN
                        CREATE TRIGGER {spec.name}
                        BEFORE {spec.event} ON {spec.table}
                        FOR EACH ROW EXECUTE FUNCTION dem_tier_a_guard();
                    END IF;
                END
                $dem_trigger$
                """
            )
        return
    raise RuntimeError(f"Tier A triggers do not support dialect {dialect!r}")


def drop_tier_a_trigger_specs(
    connection: Connection, specs: tuple[TriggerSpec, ...]
) -> None:
    """Remove selected Tier A trigger specs without dropping the shared function."""
    dialect = connection.dialect.name
    if dialect == "sqlite":
        for spec in reversed(specs):
            connection.exec_driver_sql(f"DROP TRIGGER IF EXISTS {spec.name}")
        return
    if dialect == "postgresql":
        for spec in reversed(specs):
            connection.exec_driver_sql(
                f"DROP TRIGGER IF EXISTS {spec.name} ON {spec.table}"
            )
        return
    raise RuntimeError(f"Tier A triggers do not support dialect {dialect!r}")


def proven_without_verified_proof(connection: Connection) -> list[int]:
    """List theorems marked proven that have no verified proof."""
    return list(connection.scalars(text(PROVEN_WITHOUT_VERIFIED_PROOF_SQL)))


def create_proven_requires_verified_triggers(connection: Connection) -> None:
    """Install the D7 guards after checking that existing rows satisfy them."""
    offending = proven_without_verified_proof(connection)
    if offending:
        raise RuntimeError(
            "cannot install the proven-requires-verified guard: theorem "
            f"{offending[0]} is proven without a verified proof"
        )
    create_tier_a_triggers(connection, PROVEN_REQUIRES_VERIFIED_TRIGGER_SPECS)


def drop_tier_a_triggers(connection: Connection) -> None:
    """Remove all Tier A guards during an Alembic downgrade."""
    drop_tier_a_trigger_specs(connection, TIER_A_TRIGGER_SPECS)
    if connection.dialect.name == "postgresql":
        connection.exec_driver_sql("DROP FUNCTION IF EXISTS dem_tier_a_guard()")


def _create_metadata_triggers(
    target: MetaData, connection: Connection, **kw: object
) -> None:
    del target, kw
    create_tier_a_triggers(connection)
    create_tier_b_wellformed_gate(connection)
    create_tier_b_immutability_triggers(connection)


def register_metadata_triggers(metadata: MetaData) -> None:
    """Attach the shared trigger installer to every ``create_all`` schema."""
    event.listen(metadata, "after_create", _create_metadata_triggers)
