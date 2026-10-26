"""Individual published-guard probes with API payloads and archive evidence.

The draft proof probe intentionally freezes a supplementary, unfinished proof
through the existing publisher (not beta_base's completed-base publisher).
This reaches the INSERT guard, independently of the verified-proof Tier A gate.
"""
import os

import pytest
from sqlalchemy import select

from dem.db.models import Axiom, AxiomSystem, PackageRelease, Symbol, Theorem
from dem.services.package import dependency_closure, publish_release
from dem.db.package_triggers import PUBLISHED_GUARDS
from beta2_support import base_api, digests, request, report
from test_beta_writes import accepted, reset_admission

from beta_fixture import base_phase
SEED_PHASE = base_phase()
GUARDS = ("published_axiom_system_member_insert", "published_symbol_update",
          "published_theorem_update", "published_proof_step_insert")


@pytest.mark.parametrize("guard", GUARDS)
@pytest.mark.parametrize("enabled", [False, True])
def test_guard_matrix(base_api, monkeypatch, enabled, guard):
    api = base_api
    with api.transaction() as dem:
        axiom = dem.session.scalar(select(Axiom).order_by(Axiom.id))
        symbol_id = dem.session.scalar(select(Symbol.id).order_by(Symbol.id))
        theorem_id = dem.session.scalar(select(Theorem.id).order_by(Theorem.id))
        system_id = dem.session.scalar(select(AxiomSystem.id).order_by(AxiomSystem.id))
        release_id, formula_id, axiom_id = axiom.release_id, axiom.formula_id, axiom.id
        draft = dem.theorems.register("supplementary-frozen-draft", formula_id)
        draft.release_id = release_id
        draft_proof = dem.proofs.create_proof(draft.id)
        draft_proof.release_id = release_id
        draft_proof_id = draft_proof.id
        releases = list(dem.session.scalars(select(PackageRelease.id)))
        # Exact closure size gives a topological order, without package names.
        for rid in sorted(releases, key=lambda rid: (len(dependency_closure(dem.session, rid)), rid)):
            publish_release(dem.session, rid)
    user_axiom = accepted("POST", "/axioms", {"name": "guard-probe-user-axiom", "formula_id": formula_id})
    rows = {
        "published_axiom_system_member_insert": ("POST", f"/axiom-systems/{system_id}/members", {"axiom_id": user_axiom["id"]}),
        "published_symbol_update": ("PATCH", f"/symbols/{symbol_id}/latex-template", {"latex_template": "\\mathrm{guardprobe}"}),
        "published_theorem_update": ("PATCH", f"/theorems/{theorem_id}/description", {"description": "guard probe replacement"}),
        "published_proof_step_insert": ("POST", f"/proofs/{draft_proof_id}/steps", {"kind": "axiom", "axiom_id": axiom_id}),
    }
    before = digests(api)
    # This switch is used ONLY by the local mutation runner on disposable
    # copies, never to install or weaken production guards.
    if os.environ.get("BETA2_DROP_GUARD") == guard:
        table = next(g.table for g in PUBLISHED_GUARDS if g.name == guard)
        with api.engine.begin() as connection:
            connection.exec_driver_sql(f"DROP TRIGGER {guard}" + (f" ON {table}" if connection.dialect.name == "postgresql" else ""))
    reset_admission(monkeypatch, enabled)
    method, path, body = rows[guard]
    status, response, _ = request(method, path, body)
    after = digests(api)
    report(f"guard-{api.engine.dialect.name}-{enabled}-{guard}", dict(method=method, path=path, body=body, status=status, response=response, digest_unchanged=after == before))
    assert after == before, ("published digest changed", guard, method, path, body, status, response)
    assert 400 <= status < 500, (guard, method, path, body, status, response)
