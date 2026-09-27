"""`GET /formulas/batch` -- formulas with tokens for many ids in one read.

The theorem statement and the theorem search results used to send one
`GET /formulas/{id}` per formula. The tests go through the ASGI app, not the
router function, because the route has to be declared ahead of
`/formulas/{ref}` and the id list is validated by the query parameter.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dem.api import DemServices
from dem.db.models.language import Formula
from webapi.deps import dem_services
from webapi.main import app
from webapi.routers.formulas import BATCH_MAX_IDS

SEED_PHASE = "l2"


@pytest.fixture
def get(seeded_session: Session):
    dem = DemServices(seeded_session)
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[dem_services] = lambda: dem

    def get(path: str, query: str = ""):
        async def request():
            scope = {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.4"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "root_path": "",
                "query_string": query.encode(),
                "headers": [(b"host", b"test")],
                "server": ("test", 80),
                "client": ("test", 1234),
            }
            messages = []

            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(message):
                messages.append(message)

            await asyncio.wait_for(app(scope, receive, send), timeout=30)
            start = next(item for item in messages if item["type"] == "http.response.start")
            body = b"".join(
                item.get("body", b"") for item in messages if item["type"] == "http.response.body"
            )
            return start["status"], json.loads(body)

        return asyncio.run(request())

    try:
        yield get
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def _formula_ids(session: Session, count: int) -> list[int]:
    """The longest formulas, so token order is exercised on more than a few rows."""
    return list(
        session.scalars(
            select(Formula.id).order_by(Formula.token_count.desc(), Formula.id).limit(count)
        )
    )


def test_returns_each_formula_once_ordered_by_id(seeded_session: Session, get) -> None:
    ids = _formula_ids(seeded_session, 5)
    requested = [*reversed(ids), ids[0]]

    status, body = get("/formulas/batch", "ids=" + ",".join(map(str, requested)))

    assert status == 200
    assert [formula["id"] for formula in body] == sorted(ids)


def test_matches_the_single_formula_read(seeded_session: Session, get) -> None:
    ids = _formula_ids(seeded_session, 5)

    _, body = get("/formulas/batch", "ids=" + ",".join(map(str, ids)))

    for formula in body:
        status, single = get(f"/formulas/{formula['id']}")
        assert status == 200
        assert formula == single
        assert [token["position"] for token in formula["tokens"]] == list(
            range(formula["token_count"])
        )
    assert max(formula["token_count"] for formula in body) > 1


def test_leaves_out_unknown_ids(seeded_session: Session, get) -> None:
    known = _formula_ids(seeded_session, 2)
    missing = seeded_session.scalar(select(func.max(Formula.id))) + 1

    status, body = get("/formulas/batch", f"ids={missing},{known[0]},{known[1]}")

    assert status == 200
    assert [formula["id"] for formula in body] == sorted(known)
    assert get("/formulas/batch", f"ids={missing}") == (200, [])


def test_bounds_the_number_of_ids(get) -> None:
    at_limit = ",".join(str(id) for id in range(1, BATCH_MAX_IDS + 1))
    assert get("/formulas/batch", f"ids={at_limit}")[0] == 200
    assert get("/formulas/batch", f"ids={at_limit},{BATCH_MAX_IDS + 1}")[0] == 422
    # Duplicates do not count against the bound.
    assert get("/formulas/batch", f"ids={at_limit},1")[0] == 200


@pytest.mark.parametrize("query", ["", "ids=", "ids=1,,2", "ids=0", "ids=a", "ids=1 2"])
def test_rejects_a_malformed_id_list(get, query: str) -> None:
    assert get("/formulas/batch", query)[0] == 422


def test_keeps_the_paginated_list(get) -> None:
    status, body = get("/formulas", "limit=2")
    assert status == 200
    assert [formula["id"] for formula in body] == sorted(formula["id"] for formula in body)
    assert len(body) == 2
    assert "tokens" not in body[0]
