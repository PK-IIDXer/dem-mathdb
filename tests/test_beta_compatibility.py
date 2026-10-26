"""Response matrix captured before the beta implementation."""
import asyncio
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import event

from dem.api import DemServices
from webapi.deps import dem_services
from webapi.main import app

from beta_fixture import base_phase
SEED_PHASE = base_phase()
SEED_DATABASE = "sqlite"
from beta_fixture import response_reference, response_name_length, response_limit_probe
from beta_http import asgi_request
GOLDEN = Path(__file__).with_name("beta_responses.json")


def _set_seed_tag_times(session, requests, reference):
    if reference is None:
        return
    from datetime import datetime
    from sqlalchemy import select
    from dem.db.models.tag import Tag

    status, recorded_tags = reference[requests.index(("GET", "/tags", None))]
    assert status == 200
    seeded_tags = {tag.id: tag for tag in session.scalars(select(Tag))}
    assert set(seeded_tags) == {tag["id"] for tag in recorded_tags}
    for recorded in recorded_tags:
        assert set(recorded) == {"id", "name", "created_at"}
        tag = seeded_tags[recorded["id"]]
        assert tag.name == recorded["name"]
        # Only the writable fixture's input time changes; IDs, names, ordering
        # and every response field remain subject to the complete comparison.
        tag.created_at = datetime.fromisoformat(recorded["created_at"])
    session.flush()


@pytest.mark.parametrize("enabled", [False, True])
def test_original_response_matrix(fresh_seeded_session, monkeypatch, enabled):
    monkeypatch.delenv("DEM_READ_ONLY", raising=False)
    if enabled:
        monkeypatch.setenv("DEM_BETA", "1")
    else:
        monkeypatch.delenv("DEM_BETA", raising=False)
    if enabled and not os.environ.get("DEM_CAPTURE_BETA_BASELINE"):
        from webapi.beta import SESSION_KEY, Limits
        fresh_seeded_session.info[SESSION_KEY] = Limits()
    # Fix only the timestamp of newly inserted tags, so entire response bodies
    # (including timestamps) can be compared without normalizing any output.
    from datetime import datetime, timezone
    from dem.db.models.tag import Tag
    def fixed_time(mapper, connection, target):
        target.created_at = datetime(2026, 10, 21, tzinfo=timezone.utc)
    event.listen(Tag, "before_insert", fixed_time)
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[dem_services] = lambda: DemServices(fresh_seeded_session)
    requests = [
        ("GET", "/health", None),
        ("GET", "/tags", None),
        ("POST", "/tags", {"name": "a" * 120}),
        ("POST", "/tags", {"name": "b" * response_name_length()}),
        ("POST", "/tags", {}),
        ("GET", "/proofs/999999999", None),
        ("POST", "/formulas", {"tokens": []}),
        ("POST", "/formulas/parse", {"text": "???", "context": {}}),
        ("POST", "/formulas/print", {"tokens": []}),
        ("POST", "/proofs", {"theorem_id": 999999999}),
    ]
    try:
        expected = response_reference()
        _set_seed_tag_times(fresh_seeded_session, requests, expected)
        if expected is None:
            # The public tree has no pre-beta golden snapshot. Execute the
            # identical bounded requests with beta disabled, then undo every
            # write before measuring the requested mode on the same fixture.
            baseline = fresh_seeded_session.begin_nested()
            monkeypatch.delenv("DEM_BETA", raising=False)
            expected = []
            for method, path, body in requests:
                status, result, _ = asyncio.run(asgi_request(app, method, path, body))
                expected.append([status, result])
            baseline.rollback()
            if enabled:
                monkeypatch.setenv("DEM_BETA", "1")
        responses = []
        for method, path, body in requests:
            savepoint = fresh_seeded_session.begin_nested()
            status, result, _ = asyncio.run(asgi_request(app, method, path, body))
            if isinstance(result, dict) and result.get("code") == "beta.limit_exceeded":
                savepoint.rollback()
            else:
                savepoint.commit()
            responses.append([status, result])
        if os.environ.get("DEM_CAPTURE_BETA_BASELINE"):
            GOLDEN.write_text(json.dumps(responses, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            for index, (actual, old) in enumerate(zip(responses, expected, strict=True)):
                if enabled and index == 3 and response_limit_probe():
                    assert actual[0] == 422 and actual[1]["code"] == "beta.limit_exceeded"
                else:
                    assert actual == old, requests[index]
    finally:
        event.remove(Tag, "before_insert", fixed_time)
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
