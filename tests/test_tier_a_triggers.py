"""Tier A database guards across both dialects and schema origins."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dem.db.engine import make_engine
from dem.db.triggers import (
    SQLITE_TIER_B_TRIGGER_SPECS,
    TIER_A_TRIGGER_SPECS,
    TIER_B_IMMUTABILITY_TRIGGER_SPECS,
)
from scripts.build_workspace_template import build_workspace_template


_TEST_DATABASE_ENV = "DEM_TEST_DATABASE"
_CONTENT_TABLE_KEYS = {
    "proof_step": ("proof_id", "ord"),
    "proof_step_arg": ("proof_id", "step_ord", "arg_ord"),
    "proof_step_subst_term": ("proof_id", "step_ord", "source_symbol_id"),
    "proof_step_subst_prop": ("proof_id", "step_ord", "source_symbol_id"),
    "proof_step_subst_prop_param": (
        "proof_id",
        "step_ord",
        "source_symbol_id",
        "ord",
    ),
}
_CONTENT_GUARD_MESSAGE = (
    "proof content may only be edited while the proof is draft"
)


def _assert_forbidden(
    session: Session,
    sql: str,
    params: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(IntegrityError, match=message):
        with session.begin_nested():
            session.execute(text(sql), params)


def _where(keys: tuple[str, ...]) -> str:
    return " AND ".join(f"{key} = :{key}" for key in keys)


def _exercise_guards(database_url: str, origin: str) -> None:
    engine = make_engine(database_url)
    try:
        with Session(engine) as session, session.begin():
            verified = session.execute(
                text(
                    "SELECT proof.id AS proof_id, theorem.id AS theorem_id, "
                    "theorem.conclusion_formula_id AS conclusion_formula_id "
                    "FROM proof JOIN theorem ON theorem.id = proof.theorem_id "
                    "WHERE proof.status = 'verified' AND theorem.status = 'proven' "
                    "ORDER BY proof.id LIMIT 1"
                )
            ).mappings().one()
            alternative_formula_id = session.scalar(
                text(
                    "SELECT id FROM formula WHERE id <> :formula_id "
                    "ORDER BY id LIMIT 1"
                ),
                {"formula_id": verified["conclusion_formula_id"]},
            )
            assert alternative_formula_id is not None, origin

            alternative_theorem_id = session.scalar(
                text(
                    "SELECT id FROM theorem WHERE id <> :theorem_id "
                    "ORDER BY id LIMIT 1"
                ),
                {"theorem_id": verified["theorem_id"]},
            )
            assert alternative_theorem_id is not None, origin

            _assert_forbidden(
                session,
                "UPDATE theorem SET conclusion_formula_id = :formula_id "
                "WHERE id = :theorem_id",
                {
                    "formula_id": alternative_formula_id,
                    "theorem_id": verified["theorem_id"],
                },
                "theorem conclusion is immutable",
            )
            _assert_forbidden(
                session,
                "UPDATE proof SET status = 'draft' WHERE id = :proof_id",
                {"proof_id": verified["proof_id"]},
                "a verified proof cannot be demoted",
            )
            _assert_forbidden(
                session,
                "UPDATE proof SET theorem_id = :theorem_id WHERE id = :proof_id",
                {
                    "theorem_id": alternative_theorem_id,
                    "proof_id": verified["proof_id"],
                },
                "a verified proof cannot change theorem",
            )
            _assert_forbidden(
                session,
                "DELETE FROM proof WHERE id = :proof_id",
                {"proof_id": verified["proof_id"]},
                "a verified proof cannot be deleted",
            )
            _assert_forbidden(
                session,
                "DELETE FROM theorem WHERE id = :theorem_id",
                {"theorem_id": verified["theorem_id"]},
                "a proven theorem cannot be deleted",
            )

            referenced_axiom = session.execute(
                text(
                    "SELECT axiom.id, axiom.formula_id FROM axiom "
                    "JOIN proof_step ON proof_step.axiom_id = axiom.id "
                    "ORDER BY axiom.id LIMIT 1"
                )
            ).mappings().one()
            axiom_alternative_formula_id = session.scalar(
                text(
                    "SELECT id FROM formula WHERE id <> :formula_id "
                    "ORDER BY id LIMIT 1"
                ),
                {"formula_id": referenced_axiom["formula_id"]},
            )
            assert axiom_alternative_formula_id is not None, origin
            _assert_forbidden(
                session,
                "UPDATE axiom SET formula_id = :formula_id WHERE id = :axiom_id",
                {
                    "formula_id": axiom_alternative_formula_id,
                    "axiom_id": referenced_axiom["id"],
                },
                "axiom formula is immutable",
            )
            with pytest.raises(IntegrityError):
                with session.begin_nested():
                    session.execute(
                        text("DELETE FROM axiom WHERE id = :axiom_id"),
                        {"axiom_id": referenced_axiom["id"]},
                    )

            premise = session.execute(
                text(
                    "SELECT theorem_id, ord, formula_id FROM theorem_premise "
                    "ORDER BY theorem_id, ord LIMIT 1"
                )
            ).mappings().one()
            _assert_forbidden(
                session,
                "UPDATE theorem_premise SET formula_id = :formula_id "
                "WHERE theorem_id = :theorem_id AND ord = :ord",
                {**premise, "formula_id": alternative_formula_id},
                "theorem premises are immutable",
            )
            _assert_forbidden(
                session,
                "DELETE FROM theorem_premise "
                "WHERE theorem_id = :theorem_id AND ord = :ord",
                dict(premise),
                "theorem premises are immutable",
            )
            next_premise_ord = session.scalar(
                text(
                    "SELECT COALESCE(MAX(ord), -1) + 1 FROM theorem_premise "
                    "WHERE theorem_id = :theorem_id"
                ),
                {"theorem_id": verified["theorem_id"]},
            )
            _assert_forbidden(
                session,
                "INSERT INTO theorem_premise (theorem_id, ord, formula_id) "
                "VALUES (:theorem_id, :ord, :formula_id)",
                {
                    "theorem_id": verified["theorem_id"],
                    "ord": next_premise_ord,
                    "formula_id": verified["conclusion_formula_id"],
                },
                "cannot add a premise to a theorem with a verified proof",
            )

            for table, keys in _CONTENT_TABLE_KEYS.items():
                row = session.execute(
                    text(
                        f"SELECT content.* FROM {table} AS content "
                        "JOIN proof ON proof.id = content.proof_id "
                        "WHERE proof.status = 'verified' LIMIT 1"
                    )
                ).mappings().first()
                assert row is not None, f"{origin}: no verified row in {table}"
                params = {key: row[key] for key in keys}
                clause = _where(keys)
                _assert_forbidden(
                    session,
                    f"INSERT INTO {table} SELECT * FROM {table} WHERE {clause}",
                    params,
                    _CONTENT_GUARD_MESSAGE,
                )
                _assert_forbidden(
                    session,
                    f"UPDATE {table} SET proof_id = proof_id WHERE {clause}",
                    params,
                    _CONTENT_GUARD_MESSAGE,
                )
                _assert_forbidden(
                    session,
                    f"DELETE FROM {table} WHERE {clause}",
                    params,
                    _CONTENT_GUARD_MESSAGE,
                )

            session.execute(
                text("UPDATE theorem SET remarks = :remarks WHERE id = :theorem_id"),
                {
                    "remarks": "Tier A allowed theorem update",
                    "theorem_id": verified["theorem_id"],
                },
            )
            proof_name = "Tier A allowed proof update"
            session.execute(
                text(
                    "UPDATE proof SET name = :name, remarks = :remarks, "
                    "updated_at = updated_at WHERE id = :proof_id"
                ),
                {
                    "name": proof_name,
                    "remarks": proof_name,
                    "proof_id": verified["proof_id"],
                },
            )
            assert session.execute(
                text("SELECT name, remarks FROM proof WHERE id = :proof_id"),
                {"proof_id": verified["proof_id"]},
            ).one() == (proof_name, proof_name)

            namespace_id = session.scalar(
                text("SELECT namespace_id FROM theorem WHERE id = :theorem_id"),
                {"theorem_id": verified["theorem_id"]},
            )
            conjecture_id = session.scalar(
                text(
                    "INSERT INTO theorem "
                    "(public_id, namespace_id, name, conclusion_formula_id, status) "
                    "VALUES (:public_id, :namespace_id, :name, :formula_id, "
                    "'conjecture') RETURNING id"
                ),
                {
                    "public_id": str(uuid4()),
                    "namespace_id": namespace_id,
                    "name": f"Tier A disposable conjecture {uuid4()}",
                    "formula_id": verified["conclusion_formula_id"],
                },
            )
            session.execute(
                text(
                    "INSERT INTO theorem_premise (theorem_id, ord, formula_id) "
                    "VALUES (:theorem_id, 0, :formula_id)"
                ),
                {
                    "theorem_id": conjecture_id,
                    "formula_id": verified["conclusion_formula_id"],
                },
            )
            session.execute(
                text("DELETE FROM theorem WHERE id = :theorem_id"),
                {"theorem_id": conjecture_id},
            )
            assert session.scalar(
                text(
                    "SELECT COUNT(*) FROM theorem_premise "
                    "WHERE theorem_id = :theorem_id"
                ),
                {"theorem_id": conjecture_id},
            ) == 0

            identity_ordinal = session.scalar(
                text(
                    "SELECT COALESCE(MAX(identity_ordinal), -1) + 1000 "
                    "FROM proof WHERE theorem_id = :theorem_id"
                ),
                {"theorem_id": premise["theorem_id"]},
            )
            draft_id = session.scalar(
                text(
                    "INSERT INTO proof "
                    "(public_id, theorem_id, identity_ordinal, status) "
                    "VALUES (:public_id, :theorem_id, :identity_ordinal, 'draft') "
                    "RETURNING id"
                ),
                {
                    "public_id": str(uuid4()),
                    "theorem_id": premise["theorem_id"],
                    "identity_ordinal": identity_ordinal,
                },
            )
            assert draft_id is not None
            for ord_ in (0, 1):
                session.execute(
                    text(
                        "INSERT INTO proof_step "
                        "(proof_id, ord, step_kind, conclusion_formula_id) "
                        "VALUES (:proof_id, :ord, 'assumption', :formula_id)"
                    ),
                    {
                        "proof_id": draft_id,
                        "ord": ord_,
                        "formula_id": premise["formula_id"],
                    },
                )
            session.execute(
                text(
                    "INSERT INTO proof_step_arg "
                    "(proof_id, step_ord, arg_ord, referenced_step_ord) "
                    "VALUES (:proof_id, 1, 0, 0)"
                ),
                {"proof_id": draft_id},
            )
            term_sample = session.execute(
                text(
                    "SELECT source_symbol_id, target_formula_id "
                    "FROM proof_step_subst_term LIMIT 1"
                )
            ).mappings().one()
            session.execute(
                text(
                    "INSERT INTO proof_step_subst_term "
                    "(proof_id, step_ord, source_symbol_id, target_formula_id) "
                    "VALUES (:proof_id, 1, :source_symbol_id, :target_formula_id)"
                ),
                {"proof_id": draft_id, **term_sample},
            )
            prop_sample = session.execute(
                text(
                    "SELECT prop.source_symbol_id, prop.body_formula_id, "
                    "param.formal_param_symbol_id "
                    "FROM proof_step_subst_prop AS prop "
                    "JOIN proof_step_subst_prop_param AS param "
                    "ON param.proof_id = prop.proof_id "
                    "AND param.step_ord = prop.step_ord "
                    "AND param.source_symbol_id = prop.source_symbol_id "
                    "LIMIT 1"
                )
            ).mappings().one()
            session.execute(
                text(
                    "INSERT INTO proof_step_subst_prop "
                    "(proof_id, step_ord, source_symbol_id, body_formula_id) "
                    "VALUES (:proof_id, 1, :source_symbol_id, :body_formula_id)"
                ),
                {"proof_id": draft_id, **prop_sample},
            )
            session.execute(
                text(
                    "INSERT INTO proof_step_subst_prop_param "
                    "(proof_id, step_ord, source_symbol_id, ord, "
                    "formal_param_symbol_id) "
                    "VALUES (:proof_id, 1, :source_symbol_id, 0, "
                    ":formal_param_symbol_id)"
                ),
                {"proof_id": draft_id, **prop_sample},
            )
            for table in _CONTENT_TABLE_KEYS:
                session.execute(
                    text(
                        f"UPDATE {table} SET proof_id = proof_id "
                        "WHERE proof_id = :proof_id"
                    ),
                    {"proof_id": draft_id},
                )

            session.execute(
                text("DELETE FROM proof WHERE id = :proof_id"),
                {"proof_id": draft_id},
            )
            for table in _CONTENT_TABLE_KEYS:
                assert session.scalar(
                    text(f"SELECT COUNT(*) FROM {table} WHERE proof_id = :proof_id"),
                    {"proof_id": draft_id},
                ) == 0, f"{origin}: draft cascade left rows in {table}"
    finally:
        engine.dispose()


def test_tier_a_guards_match_for_alembic_and_create_all_origins(
    seed_snapshot_factory,
) -> None:
    database = os.environ.get(_TEST_DATABASE_ENV, "sqlite").lower()
    with seed_snapshot_factory.l2_origin_urls(database) as urls:
        for origin, database_url in zip(("alembic", "create_all"), urls):
            _exercise_guards(database_url, origin)


def test_workspace_template_contains_working_tier_a_guards(tmp_path: Path) -> None:
    destination = tmp_path / "workspace-template.db"
    build_workspace_template(destination)
    engine = make_engine(f"sqlite+pysqlite:///{destination.as_posix()}")
    try:
        with engine.connect() as connection:
            trigger_count = connection.scalar(
                text("SELECT COUNT(*) FROM sqlite_master WHERE type = 'trigger'")
            )
            assert trigger_count == (
                len(TIER_A_TRIGGER_SPECS)
                + len(SQLITE_TIER_B_TRIGGER_SPECS)
                + len(TIER_B_IMMUTABILITY_TRIGGER_SPECS)
            )
            proposition_type_id = connection.scalar(
                text("SELECT id FROM formula_type WHERE code = 'proposition'")
            )
            assert proposition_type_id is not None
            formula_id = connection.scalar(
                text(
                    "INSERT INTO formula "
                    "(public_id, formula_type_id, hash, token_count) "
                    "VALUES (:public_id, :formula_type_id, :hash, 1) RETURNING id"
                ),
                {
                    "public_id": str(uuid4()),
                    "formula_type_id": proposition_type_id,
                    "hash": uuid4().hex,
                },
            )
            with pytest.raises(IntegrityError, match="formula is not well-formed"):
                connection.execute(
                    text(
                        "INSERT INTO formula_token "
                        "(formula_id, position, de_bruijn_index) "
                        "VALUES (:formula_id, 0, 0)"
                    ),
                    {"formula_id": formula_id},
                )
    finally:
        engine.dispose()
