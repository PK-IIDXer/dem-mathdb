"""Theorem response projections preserve premise order and batch the read."""

import asyncio

import pytest
from fastapi import FastAPI
from sqlalchemy import event

from beta_http import asgi_request
from dem.api import DemServices
from dem.types import PremiseStepInput, TheoremStepInput
from webapi.deps import dem_services
from webapi.routers.theorems import router
from webapi.theorem_output import theorem_outputs

SEED_PHASE = "public_demo"


@pytest.fixture
def statements(fresh_seeded_session):
    dem = DemServices(fresh_seeded_session)
    formulas = [dem.formulas.register(dem.formulas.parse_text(text)[0]).id
                for text in ("φ", "ψ", "χ")]
    premise_ids = sorted(formulas, reverse=True)
    conclusion = premise_ids[0]
    empty = dem.theorems.register("Display fixture without premises", conclusion)
    lemma = dem.theorems.register("Display fixture with premises", conclusion, premise_ids)
    citation = dem.theorems.register("Display fixture citing the lemma", conclusion, premise_ids)
    lemma_proof = dem.proofs.create_proof(lemma.id)
    dem.proofs.add_step(lemma_proof.id, PremiseStepInput(0))
    dem.proofs.validate(lemma_proof.id)
    citation_proof = dem.proofs.create_proof(citation.id)
    for ord_ in range(len(premise_ids)):
        dem.proofs.add_step(citation_proof.id, PremiseStepInput(ord_))
    dem.proofs.add_step(citation_proof.id, TheoremStepInput(lemma_proof.id, arg_step_ords=(0, 1, 2)))
    dem.proofs.validate(citation_proof.id)
    return dem, empty, lemma, citation, premise_ids


def test_projection_reads_premises_once_in_ord_order(statements):
    dem, empty, lemma, citation, premise_ids = statements
    engine = dem.session.get_bind()
    queries = []

    def record(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    for batch, expected in [
        ([], []),
        ([lemma], [premise_ids]),
        ([citation, empty, lemma], [premise_ids, [], premise_ids]),
    ]:
        queries.clear()
        event.listen(engine, "before_cursor_execute", record)
        try:
            outputs = theorem_outputs(dem.session, batch)
        finally:
            event.remove(engine, "before_cursor_execute", record)
        assert [output.id for output in outputs] == [theorem.id for theorem in batch]
        assert [output.premise_formula_ids for output in outputs] == expected
        assert sum("FROM theorem_premise" in query for query in queries) == bool(batch)


def test_theorem_routes_include_premise_ids(statements):
    dem, empty, lemma, citation, premise_ids = statements
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[dem_services] = lambda: dem

    def get(path, query=b""):
        async def application(scope, receive, send):
            await app({**scope, "query_string": query}, receive, send)

        status, payload, _ = asyncio.run(asgi_request(application, "GET", path))
        assert status == 200, payload
        return payload

    for path in (f"/theorems/{lemma.id}", f"/theorems/by-name/{lemma.name}",
                 f"/theorems/public/{lemma.public_id}"):
        assert get(path)["premise_formula_ids"] == premise_ids
    assert get(f"/theorems/{empty.id}")["premise_formula_ids"] == []

    for query in (b"", b"search=Display+fixture", b"search=Display+fixture&limit=20"):
        results = {row["id"]: row["premise_formula_ids"] for row in get("/theorems", query)}
        assert {empty.id: [], lemma.id: premise_ids, citation.id: premise_ids}.items() <= results.items()

    used_in = get(f"/theorems/{lemma.id}/used-in-theorems")
    assert [(row["id"], row["premise_formula_ids"]) for row in used_in] == [(citation.id, premise_ids)]


def test_public_implication_chain_keeps_three_ordered_premises(seeded_session):
    dem = DemServices(seeded_session)
    chain = dem.theorems.get_by_name("含意の連鎖")
    expected = [dem.formulas.register(dem.formulas.parse_text(text)[0]).id
                for text in ("φ → ψ", "ψ → χ", "φ")]
    assert theorem_outputs(seeded_session, [chain])[0].premise_formula_ids == expected

