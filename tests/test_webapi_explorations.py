from __future__ import annotations

import asyncio
import json
from urllib.parse import urlencode

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from dem.api import DemServices
from dem.db.models.language import Formula, FormulaType
from dem.db.models.theorem import Theorem
from webapi.deps import dem_services
from webapi.main import app


SEED_PHASE = "public_core"
SEED_DATABASE = "sqlite"


@pytest.fixture
def exploration_api(fresh_seeded_session: Session):
    dem = DemServices(fresh_seeded_session)
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[dem_services] = lambda: dem

    def request(
        method: str,
        path: str,
        body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> tuple[int, object]:
        async def run() -> tuple[int, object]:
            payload = json.dumps(body).encode() if body is not None else b""
            query = urlencode(params or {}).encode()
            scope = {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.4"},
                "http_version": "1.1",
                "method": method,
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "root_path": "",
                "query_string": query,
                "headers": [
                    (b"host", b"test"),
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode()),
                ],
                "server": ("test", 80),
                "client": ("test", 1234),
            }
            messages: list[dict[str, object]] = []
            sent = False

            async def receive():
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": payload, "more_body": False}
                await asyncio.Event().wait()

            async def send(message):
                messages.append(message)

            await asyncio.wait_for(app(scope, receive, send), timeout=30)
            start = next(item for item in messages if item["type"] == "http.response.start")
            response_body = b"".join(
                item.get("body", b"")
                for item in messages
                if item["type"] == "http.response.body"
            )
            return int(start["status"]), json.loads(response_body)

        return asyncio.run(run())

    try:
        yield dem, request
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_exploration_endpoints_create_read_depend_and_promote(exploration_api) -> None:
    dem, request = exploration_api
    premise = dem.session.scalar(
        select(Formula)
        .join(FormulaType)
        .where(FormulaType.name == "命題")
        .order_by(Formula.id)
    )
    status, note = request(
        "POST",
        "/explorations",
        {"name": "api-note", "premise_formula_ids": [premise.id]},
    )
    assert status == 201, note
    assert note["theorem"]["name"] == "api-note"
    assert note["proof"]["status"] == "draft"
    assert [item["id"] for item in note["premises"]] == [premise.id]

    status, listed = request("GET", "/explorations")
    assert status == 200
    assert [item["theorem"]["name"] for item in listed] == ["api-note"]
    status, _ = request("GET", f"/explorations/{note['theorem']['public_id']}")
    assert status == 200

    status, step = request(
        "POST",
        f"/proofs/{note['proof']['id']}/steps",
        {
            "kind": "premise",
            "premise_ord": 0,
            "conclusion_formula_id": premise.id,
        },
    )
    assert status == 201, step
    step_ord = step["ord"]

    status, validation = request("POST", f"/proofs/{note['proof']['id']}/validate")
    assert status == 422
    assert validation["code"] == "exploration.no_final_validation"

    status, dependencies = request(
        "GET",
        f"/explorations/{note['theorem']['id']}/steps/{step_ord}/dependencies"
    )
    assert status == 200
    assert dependencies == {"axioms": [], "theorems": []}

    status, promoted = request(
        "POST",
        f"/explorations/{note['theorem']['id']}/steps/{step_ord}/promote",
        {"name": "api-promoted"},
    )
    assert status == 201, promoted
    assert promoted["theorem"]["status"] == "proven"
    assert promoted["proof"]["status"] == "verified"

    status, visible = request("GET", "/theorems", params={"search": "api-"})
    assert status == 200
    assert [item["name"] for item in visible] == ["api-promoted"]
    status, tags = request("GET", "/tags")
    assert status == 200
    assert "system:exploration" not in {item["name"] for item in tags}


def test_exploration_promotion_error_exposes_stable_code(exploration_api) -> None:
    dem, request = exploration_api
    formula = dem.session.scalar(
        select(Formula)
        .join(FormulaType)
        .where(FormulaType.name == "命題")
        .order_by(Formula.id)
    )
    _, note = request(
        "POST", "/explorations", {"name": "api-open", "premise_formula_ids": []}
    )
    _, step = request(
        "POST",
        f"/proofs/{note['proof']['id']}/steps",
        {"kind": "assumption", "conclusion_formula_id": formula.id},
    )

    status, rejected = request(
        "POST",
        f"/explorations/{note['theorem']['id']}/steps/{step['ord']}/promote",
        {"name": "api-must-not-exist"},
    )
    assert status == 422
    assert rejected["code"] == "exploration.open_assumption"
    assert not list(
        dem.session.scalars(select(Theorem).where(Theorem.name == "api-must-not-exist"))
    )


def test_public_stats_match_database_and_exclude_notes(exploration_api, monkeypatch):
    from dem.db.models.definition import Definition
    from dem.db.models.inference import Axiom, AxiomSystem
    from dem.db.models.tag import Tag, TheoremTag
    from dem.db.models.theorem import Proof, ProofStep
    from dem.services.system_tags import EXPLORATION_TAG
    from dem.types import PremiseStepInput, TheoremStepInput

    dem, request = exploration_api
    session = dem.session
    premise = session.scalar(select(Formula).join(FormulaType).where(FormulaType.name == "命題"))
    cited = dem.theorems.register("stats-cited", premise.id, [premise.id])
    cited_proof = dem.proofs.create_proof(cited.id)
    dem.proofs.add_step(cited_proof.id, PremiseStepInput(0), premise.id)
    dem.proofs.validate(cited_proof.id)
    citing = dem.theorems.register("stats-citing", premise.id, [premise.id])
    # Multiple citations and proofs still make only one theorem pair.
    for _ in range(2):
        proof = dem.proofs.create_proof(citing.id)
        dem.proofs.add_step(proof.id, PremiseStepInput(0), premise.id)
        for _ in range(2):
            dem.proofs.add_step(proof.id, TheoremStepInput(cited_proof.id, arg_step_ords=(0,)), premise.id)
    before = request("GET", "/stats")
    assert before[0] == 200
    note = dem.explorations.create("stats-hidden", [premise.id])
    dem.proofs.add_step(note.proof.id, PremiseStepInput(0), premise.id)
    dem.proofs.add_step(note.proof.id, TheoremStepInput(cited_proof.id, arg_step_ords=(0,)), premise.id)
    session.flush()
    # Independent row/set derivation, without the production visibility helper.
    hidden = set(session.scalars(select(TheoremTag.theorem_id).join(Tag).where(Tag.name == EXPLORATION_TAG)))
    theorems = [row for row in session.execute(select(Theorem.id, Theorem.status)) if row.id not in hidden]
    visible = {row.id for row in theorems}
    proofs = {row.id: row for row in session.execute(select(Proof.id, Proof.theorem_id, Proof.status))}
    steps = [row for row in session.execute(select(ProofStep.proof_id, ProofStep.step_kind, ProofStep.applied_proof_id)) if proofs[row.proof_id].theorem_id in visible]
    pairs = {
        (proofs[row.proof_id].theorem_id, proofs[row.applied_proof_id].theorem_id)
        for row in steps if row.step_kind == "theorem"
        and proofs[row.proof_id].theorem_id != proofs[row.applied_proof_id].theorem_id
    }
    expected = {
        "theorem_count": len(theorems),
        "proven_theorem_count": sum(row.status == "proven" for row in theorems),
        "verified_proof_count": sum(row.status == "verified" and row.theorem_id in visible for row in proofs.values()),
        "proof_step_count": len(steps),
        "dependency_count": len(pairs),
        "axiom_count": len(list(session.scalars(select(Axiom.id)))),
        "primitive_axiom_count": sum(kind == "primitive" for kind in session.scalars(select(Axiom.origin_kind))),
        "axiom_system_count": len(list(session.scalars(select(AxiomSystem.id)))),
        "definition_count": len(list(session.scalars(select(Definition.id)))),
    }
    assert (citing.id, cited.id) in pairs
    monkeypatch.setenv("DEM_READ_ONLY", "true")
    assert request("GET", "/stats") == (200, expected) == before
    assert request("GET", "/config") == (200, {"read_only": True})
