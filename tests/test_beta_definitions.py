"""The earliest definition-bearing snapshot; no later seed is rebuilt here."""
import json
import subprocess
import sys

import pytest
from sqlalchemy import select

from dem.db.models import Definition, Axiom
from beta2_support import base_api, digests, request, report
from scripts.beta_base import publish_all
from test_beta_writes import accepted, reset_admission, DEFINITION_ROUTES

from beta_fixture import definition_phase
SEED_PHASE = definition_phase()


@pytest.mark.parametrize("enabled", [False, True])
def test_published_definition_matrix(base_api, monkeypatch, enabled):
    api = base_api
    with api.transaction() as dem:
        definition = dem.session.scalar(select(Definition).order_by(Definition.id))
        assert definition is not None
        tag = dem.tags.get_or_create("beta-definition-existing")
        dem.tags.attach("definition", definition.id, tag.id)
        definition_id, tag_id = definition.id, tag.id
        formula_id = dem.session.scalar(select(Axiom.formula_id).order_by(Axiom.id))
    publish_all(api.engine)
    before = digests(api)
    if not enabled:
        completed = subprocess.run([sys.executable, "-m", "scripts.beta_base", "verify", "--database-url",
                                    api.engine.url.render_as_string(hide_password=False)],
                                   capture_output=True, text=True, timeout=60)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        verification = json.loads(completed.stdout)
        assert verification["ok"]
        report("verify-definitions-" + api.engine.dialect.name, verification)
    reset_admission(monkeypatch, enabled)
    # A logical definition of an existing proposition can refer to the base
    # without importing any foundation-specific parameter conventions.
    user = accepted("POST", "/definitions", {"kind": "logical", "name": "user-matrix-definition", "param_symbol_ids": [], "body_formula_id": formula_id})
    assert digests(api) == before
    fresh_tag = accepted("POST", "/tags", {"name": "beta-definition-new"})
    rows = [dict(method="POST", route="/definitions", user_status=201)]
    cases = [
        ("PATCH", "/definitions/{id}/description", f"/definitions/{definition_id}/description", {"description": "replacement"}, f"/definitions/{user['id']}/description"),
        ("POST", "/definitions/{id}/tags", f"/definitions/{definition_id}/tags", {"tag_id": fresh_tag["id"]}, f"/definitions/{user['id']}/tags"),
        ("DELETE", "/definitions/{id}/tags/{tag_id}", f"/definitions/{definition_id}/tags/{tag_id}", None, f"/definitions/{user['id']}/tags/{fresh_tag['id']}"),
    ]
    for method, route, path, body, user_path in cases:
        reset_admission(monkeypatch, enabled)
        snapshot = digests(api)
        status, response, _ = request(method, path, body)
        assert digests(api) == snapshot == before, ("STOP: published definition changed", method, path, body, status, response)
        assert 400 <= status < 500, (method, path, body, status, response)
        accepted(method, user_path, body)
        assert digests(api) == before
        rows.append(dict(method=method, route=route, base_status=status, user_status=200, response=response))
    assert {(row["method"], row["route"]) for row in rows} == DEFINITION_ROUTES
    report(f"definitions-{api.engine.dialect.name}-{enabled}", rows)
