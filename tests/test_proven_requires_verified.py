"""D7: a theorem is proven only through a verified proof; proofs start as drafts.

lean-import-design §3.7.  AGENTS.md requires, for a change to a validation
path, an accept / reject matrix run against the old and the new schema, and a
mutation check that removing or weakening the guard makes the test fail.

"Old" is the same database with the three D7 triggers dropped, i.e. the schema
of 20260923_0002.  Every case runs in a savepoint that is rolled back, and the
whole transaction is rolled back at the end.

Write paths audited before adding the guards (none writes 'verified' or
'proven' directly):

- ``ProofService.create_proof``: INSERT proof with status 'draft'.
- ``ProofService.validate``: UPDATE proof draft -> verified (or rejected),
  flushed, then ``TheoremService._promote_to_proven`` UPDATEs the theorem.
- ``TheoremService.register``: INSERT theorem with status 'conjecture'.
- Seeds call the services above (``hilbert_toolkit`` promotes only after
  finding a verified proof).  The REST API writes only through services.
- Workspace templates are file copies (SQLite) or ``CREATE DATABASE ...
  TEMPLATE`` (PostgreSQL); no trigger fires.
- Schema upgrades (N7.5) run Alembic; no revision writes theorem or proof
  status after the guards exist.  ``.github/scripts/migration_roundtrip.py``
  inserts proven theorems with verified proofs at 20260910_0001, before any
  guard, and 20260923_0003 accepts that state.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dem.db.engine import make_engine
from dem.db.triggers import PROVEN_REQUIRES_VERIFIED_TRIGGER_SPECS


_TEST_DATABASE_ENV = "DEM_TEST_DATABASE"
ACCEPT, REJECT = "accept", "reject"


class _Case:
    def __init__(self, session: Session, sample: dict[str, object]) -> None:
        self.session = session
        self.sample = sample

    def sql(self, statement: str, **params: object):
        return self.session.execute(text(statement), params)

    def theorem(self, status: str = "conjecture") -> int:
        return self.session.scalar(
            text(
                "INSERT INTO theorem (public_id, namespace_id, name, conclusion_formula_id, status) "
                "VALUES (:public_id, :namespace_id, :name, :formula_id, :status) RETURNING id"
            ),
            {
                "public_id": str(uuid4()),
                "namespace_id": self.sample["namespace_id"],
                "name": f"D7 matrix {uuid4()}",
                "formula_id": self.sample["formula_id"],
                "status": status,
            },
        )

    def proof(self, theorem_id: int, status: str = "draft") -> int:
        return self.session.scalar(
            text(
                "INSERT INTO proof (public_id, theorem_id, identity_ordinal, status) "
                "VALUES (:public_id, :theorem_id, 0, :status) RETURNING id"
            ),
            {"public_id": str(uuid4()), "theorem_id": theorem_id, "status": status},
        )

    def set_theorem(self, theorem_id: int, status: str) -> None:
        self.sql("UPDATE theorem SET status = :status WHERE id = :id", status=status, id=theorem_id)

    def set_proof(self, proof_id: int, status: str) -> None:
        self.sql("UPDATE proof SET status = :status WHERE id = :id", status=status, id=proof_id)


def _promote_with(proof_status: str | None) -> Callable[[_Case], None]:
    def run(case: _Case) -> None:
        theorem_id = case.theorem()
        if proof_status is not None:
            proof_id = case.proof(theorem_id)
            if proof_status != "draft":
                case.set_proof(proof_id, proof_status)
        case.set_theorem(theorem_id, "proven")

    return run


def _move_proven(case: _Case) -> None:
    namespace_id = case.session.scalar(
        text("INSERT INTO namespace (name) VALUES (:name) RETURNING id"),
        {"name": f"local.d7-{uuid4().hex[:8]}"},
    )
    case.sql(
        "UPDATE theorem SET namespace_id = :namespace_id WHERE id = :id",
        namespace_id=namespace_id,
        id=case.sample["theorem_id"],
    )


CASES: dict[str, Callable[[_Case], None]] = {
    "insert a conjecture": lambda case: case.theorem(),
    "insert a proven theorem": lambda case: case.theorem("proven"),
    "promote with no proof": _promote_with(None),
    "promote with only a draft proof": _promote_with("draft"),
    "promote with only a rejected proof": _promote_with("rejected"),
    # ProofService.validate(): the proof is flushed as verified first.
    "promote after the proof is verified": _promote_with("verified"),
    "edit remarks of a proven theorem": lambda case: case.sql(
        "UPDATE theorem SET remarks = 'D7 matrix' WHERE id = :id", id=case.sample["theorem_id"]
    ),
    "move a proven theorem to another namespace": _move_proven,
    "insert a draft proof": lambda case: case.proof(case.theorem()),
    "insert a verified proof": lambda case: case.proof(case.theorem(), "verified"),
    "insert a rejected proof": lambda case: case.proof(case.theorem(), "rejected"),
    # Not a D7 case: the database cannot run the kernel, so a raw draft ->
    # verified UPDATE stays possible; ProofService.validate() is its only writer.
    "mark a draft proof verified by raw SQL": lambda case: case.set_proof(
        case.proof(case.theorem()), "verified"
    ),
    "mark a draft proof rejected": lambda case: case.set_proof(case.proof(case.theorem()), "rejected"),
}

EXPECTED_NEW = {
    "insert a conjecture": ACCEPT,
    "insert a proven theorem": REJECT,
    "promote with no proof": REJECT,
    "promote with only a draft proof": REJECT,
    "promote with only a rejected proof": REJECT,
    "promote after the proof is verified": ACCEPT,
    "edit remarks of a proven theorem": ACCEPT,
    "move a proven theorem to another namespace": ACCEPT,
    "insert a draft proof": ACCEPT,
    "insert a verified proof": REJECT,
    "insert a rejected proof": REJECT,
    "mark a draft proof verified by raw SQL": ACCEPT,
    "mark a draft proof rejected": ACCEPT,
}
# The only differences from the old schema: D7 makes these stricter.
TIGHTENED = {
    "insert a proven theorem",
    "promote with no proof",
    "promote with only a draft proof",
    "promote with only a rejected proof",
    "insert a verified proof",
    "insert a rejected proof",
}


def _matrix(session: Session, sample: dict[str, object]) -> dict[str, str]:
    outcomes = {}
    for name, run in CASES.items():
        savepoint = session.begin_nested()
        try:
            run(_Case(session, sample))
            outcomes[name] = ACCEPT
        except IntegrityError:
            outcomes[name] = REJECT
        finally:
            savepoint.rollback()
    return outcomes


def _sample(session: Session) -> dict[str, object]:
    return dict(
        session.execute(
            text(
                "SELECT theorem.id AS theorem_id, theorem.namespace_id AS namespace_id, "
                "theorem.conclusion_formula_id AS formula_id "
                "FROM theorem JOIN proof ON proof.theorem_id = theorem.id "
                "WHERE theorem.status = 'proven' AND proof.status = 'verified' "
                "ORDER BY theorem.id LIMIT 1"
            )
        ).mappings().one()
    )


def _drop(session: Session, name: str, table: str) -> None:
    if session.get_bind().dialect.name == "sqlite":
        session.execute(text(f"DROP TRIGGER {name}"))
    else:
        session.execute(text(f"DROP TRIGGER {name} ON {table}"))


def _replace(session: Session, name: str, table: str, event: str, condition: str) -> None:
    """Replace one guard by a weaker one (a mutation)."""
    _drop(session, name, table)
    if session.get_bind().dialect.name == "sqlite":
        session.execute(
            text(
                f"CREATE TRIGGER {name} BEFORE {event} ON {table} FOR EACH ROW "
                f"WHEN {condition} BEGIN SELECT RAISE(ABORT, 'weakened'); END"
            )
        )
        return
    function = f"dem_test_weakened_{name}"
    session.execute(
        text(
            f"CREATE FUNCTION {function}() RETURNS trigger LANGUAGE plpgsql AS $$ "
            f"BEGIN IF {condition} THEN RAISE EXCEPTION 'weakened' USING ERRCODE = '23514'; "
            "END IF; RETURN NEW; END $$"
        )
    )
    session.execute(
        text(
            f"CREATE TRIGGER {name} BEFORE {event} ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION {function}()"
        )
    )


# Each mutation removes or weakens one guard; the matrix must notice it.
MUTATIONS: dict[str, Callable[[Session], None]] = {
    **{
        f"drop {spec.name}": (
            lambda session, spec=spec: _drop(session, spec.name, spec.table)
        )
        for spec in PROVEN_REQUIRES_VERIFIED_TRIGGER_SPECS
    },
    "promotion accepts any proof, verified or not": lambda session: _replace(
        session,
        "theorem_proven_requires_verified_update",
        "theorem",
        "UPDATE",
        "NEW.status = 'proven' AND NOT EXISTS (SELECT 1 FROM proof WHERE theorem_id = NEW.id)",
    ),
    "promotion accepts a verified proof of another theorem": lambda session: _replace(
        session,
        "theorem_proven_requires_verified_update",
        "theorem",
        "UPDATE",
        "NEW.status = 'proven' AND NOT EXISTS (SELECT 1 FROM proof WHERE status = 'verified')",
    ),
    "proven insert accepts any proof": lambda session: _replace(
        session,
        "theorem_proven_requires_verified_insert",
        "theorem",
        "INSERT",
        "NEW.status = 'proven' AND NOT EXISTS (SELECT 1 FROM proof)",
    ),
    "proof insert blocks only 'verified'": lambda session: _replace(
        session, "proof_insert_draft_only", "proof", "INSERT", "NEW.status = 'verified'"
    ),
}


@pytest.fixture
def origins(seed_snapshot_factory):
    database = os.environ.get(_TEST_DATABASE_ENV, "sqlite").lower()
    with seed_snapshot_factory.l2_origin_urls(database) as urls:
        yield dict(zip(("alembic", "create_all"), urls))


def _with_session(database_url: str, body: Callable[[Session], None]) -> None:
    engine = make_engine(database_url)
    try:
        with Session(engine) as session:
            session.begin()
            try:
                body(session)
            finally:
                session.rollback()
    finally:
        engine.dispose()


def test_new_schema_rejects_exactly_the_tightened_cases(origins) -> None:
    for origin, url in origins.items():

        def body(session: Session) -> None:
            assert _matrix(session, _sample(session)) == EXPECTED_NEW, origin

        _with_session(url, body)


def test_old_and_new_differ_only_by_tightening(origins) -> None:
    for origin, url in origins.items():

        def body(session: Session) -> None:
            sample = _sample(session)
            new = _matrix(session, sample)
            for spec in PROVEN_REQUIRES_VERIFIED_TRIGGER_SPECS:
                _drop(session, spec.name, spec.table)
            old = _matrix(session, sample)
            loosened = {name for name in CASES if new[name] == ACCEPT and old[name] == REJECT}
            tightened = {name for name in CASES if new[name] == REJECT and old[name] == ACCEPT}
            assert loosened == set(), origin
            assert tightened == TIGHTENED, origin

        _with_session(url, body)


@pytest.mark.parametrize("mutation", list(MUTATIONS))
def test_every_mutation_of_the_guard_is_detected(origins, mutation: str) -> None:
    url = origins["alembic"]

    def body(session: Session) -> None:
        sample = _sample(session)
        MUTATIONS[mutation](session)
        assert _matrix(session, sample) != EXPECTED_NEW

    _with_session(url, body)
