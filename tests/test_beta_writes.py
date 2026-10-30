"""Enumerate the running API and exercise every write-capable route."""
import pytest
from sqlalchemy import event, select

from dem.db.models import Base, Symbol, Axiom, AxiomSystem, Theorem, Proof, Package, PackageRelease
from dem.types import SymbolTypeName
from webapi import beta, contact
from webapi.main import app, READ_ONLY_POST_PATHS, SAFE_METHODS
from beta2_support import base_api, digests, request, report
from scripts.beta_base import publish_all

from beta_fixture import base_phase
SEED_PHASE = base_phase()

# Explicit classifications: a new route must be assigned and exercised below.
PROTECTED = {
    ("POST", "/symbols/{id}/aliases"),
    ("PATCH", "/symbols/{id}/notation"),
    ("PATCH", "/symbols/{id}/latex-template"),
    ("PATCH", "/axioms/{id}/description"),
    ("POST", "/axioms/{id}/tags"),
    ("DELETE", "/axioms/{id}/tags/{tag_id}"),
    ("POST", "/axiom-systems/{id}/members"),
    ("DELETE", "/axiom-systems/{id}/members/{axiom_id}"),
    ("PATCH", "/theorems/{id}/description"),
    ("POST", "/theorems/{id}/tags"),
    ("DELETE", "/theorems/{id}/tags/{tag_id}"),
    ("POST", "/proofs"),
    ("POST", "/proofs/{id}/steps"),
}
DEFINITION_ROUTES = {
    ("POST", "/definitions"), ("PATCH", "/definitions/{id}/description"),
    ("POST", "/definitions/{id}/tags"), ("DELETE", "/definitions/{id}/tags/{tag_id}"),
}
USER_OR_COMPUTATION = {
    ("POST", "/symbols"), ("POST", "/symbol-roles"),
    ("POST", "/formulas"), ("POST", "/formulas/validate"), ("POST", "/formulas/search"),
    ("POST", "/axioms"), ("POST", "/axiom-systems"), ("POST", "/theorems"),
    ("POST", "/proofs/{id}/validate"),
    ("POST", "/proofs/{id}/steps/suggest"), ("POST", "/proofs/{id}/steps/suggest-backward"),
    ("POST", "/proofs/compute-substituted-tokens"), ("POST", "/proofs/compute-gen-tokens"),
    ("POST", "/explorations"), ("POST", "/explorations/{ref}/steps/{step_ord}/promote"),
    ("POST", "/tags"),
}
NON_DATABASE_WRITES = {("POST", "/contact")}


def actual_writes():
    result = set()
    for included in app.routes:
        routes = included.effective_route_contexts() if hasattr(included, "effective_route_contexts") else [included]
        for route in routes:
            for method in getattr(route, "methods", ()):
                if method not in SAFE_METHODS and not (method == "POST" and route.path in READ_ONLY_POST_PATHS):
                    result.add((method, route.path))
    return result


def test_write_route_classification_is_exhaustive():
    classified = PROTECTED | DEFINITION_ROUTES | USER_OR_COMPUTATION | NON_DATABASE_WRITES
    assert actual_writes() == classified
    assert len(classified) == sum(map(len, (PROTECTED, DEFINITION_ROUTES, USER_OR_COMPUTATION, NON_DATABASE_WRITES)))


@pytest.mark.parametrize("enabled", [False, True])
def test_contact_does_not_write_mathematical_database(base_api, monkeypatch, tmp_path, enabled):
    api = base_api
    publish_all(api.engine)
    before = digests(api)
    reset_admission(monkeypatch, enabled)
    monkeypatch.setenv("DEM_BETA_CONTACT_DIR", str(tmp_path))
    monkeypatch.setattr(contact, "runtime", contact.ContactRuntime())
    statements = []
    def record(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(api.engine, "before_cursor_execute", record)
    try:
        status, response, _ = request("POST", "/contact", {"kind": "bug", "message": "Independent intake"})
    finally:
        event.remove(api.engine, "before_cursor_execute", record)
    assert statements == [], "Contact must not even query the mathematical database"
    assert digests(api) == before
    assert status == (202 if enabled else 404), response
    assert len(list(tmp_path.glob("contact-*.json"))) == int(enabled)


def accepted(method, path, body=None):
    status, response, _ = request(method, path, body)
    assert 200 <= status < 300, (method, path, body, status, response)
    return response


def reset_admission(monkeypatch, enabled):
    # Each matrix row is an independent request, not a rate-limit test.
    monkeypatch.setattr(beta, "runtime", beta.Runtime())
    if enabled:
        monkeypatch.setenv("DEM_BETA", "1")
    else:
        monkeypatch.delenv("DEM_BETA", raising=False)


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("package", ["dem.public.logic", "dem.public.natural_deduction"])
def test_published_write_matrix(base_api, monkeypatch, enabled, package):
    api = base_api
    with api.transaction() as dem:
        symbol = dem.session.scalar(select(Symbol).where(Symbol.arity == 2).order_by(Symbol.id))
        release_id = dem.session.scalar(select(PackageRelease.id).join(Package).where(Package.name == package))
        axiom = dem.session.scalar(select(Axiom).where(Axiom.release_id == release_id).order_by(Axiom.id))
        # The original logic package contains no theorem; its demos exercise that path.
        theorem = dem.session.scalar(select(Theorem).where(Theorem.release_id == release_id).order_by(Theorem.id)) if package.endswith("natural_deduction") else dem.session.scalar(select(Theorem).order_by(Theorem.id))
        proof = dem.session.scalar(select(Proof).where(Proof.theorem_id == theorem.id, Proof.status == "verified"))
        member = Base.metadata.tables["axiom_system_member"]
        system_id, member_axiom_id = dem.session.execute(select(member.c.axiom_system_id, member.c.axiom_id).join(AxiomSystem, AxiomSystem.id == member.c.axiom_system_id).where(AxiomSystem.release_id == release_id).order_by(member.c.axiom_system_id, member.c.axiom_id)).first()
        tag = dem.tags.get_or_create("beta-matrix-existing")
        for kind, row in (("axiom", axiom), ("theorem", theorem)):
            dem.tags.attach(kind, row.id, tag.id)
        notation = {"notation_kind": symbol.notation_kind, "precedence": symbol.precedence}
        changed_notation = ({"notation_kind": "prefix"} if symbol.notation_kind == "infix"
                            else {"notation_kind": "infix", "precedence": 25})
        ids = dict(symbol=symbol.id, type=symbol.symbol_type_id, axiom=axiom.id,
                   formula=axiom.formula_id, theorem=theorem.id, proof=proof.id,
                   system=system_id, member=member_axiom_id, tag=tag.id)
        tokens = [{"symbol_id": t.symbol_id, "de_bruijn_index": t.de_bruijn_index} for t in dem.formulas.get_tokens(axiom.formula_id)]
        free = dem.session.scalar(select(Symbol.id).join(Symbol.symbol_type).where(
            Base.metadata.tables["symbol_type"].c.name == SymbolTypeName.FREE_TERM_VAR.value, Symbol.arity == 0).order_by(Symbol.id))
    publish_all(api.engine)
    before = digests(api)
    reset_admission(monkeypatch, enabled)
    user_symbol = accepted("POST", "/symbols", {"name": "matrix-user-symbol", "symbol_type_id": ids["type"], "arity": 2, **notation})
    user_axiom = accepted("POST", "/axioms", {"name": "matrix-user-axiom", "formula_id": ids["formula"]})
    user_system = accepted("POST", "/axiom-systems", {"name": "matrix-user-system"})
    user_theorem = accepted("POST", "/theorems", {"name": "matrix-user-theorem", "conclusion_formula_id": ids["formula"]})
    user_proof = accepted("POST", "/proofs", {"theorem_id": user_theorem["id"]})
    fresh_tag = accepted("POST", "/tags", {"name": "matrix-user-tag"})
    assert digests(api) == before
    rows = []
    exercised = {("POST", path) for path in ("/symbols", "/axioms", "/axiom-systems", "/theorems", "/tags")}

    def check(method, route, path, body, *, user_path=None, user_body=None, expected="reject"):
        reset_admission(monkeypatch, enabled)
        snapshot = digests(api)
        status, response, _ = request(method, path, body)
        after = digests(api)
        # If this assertion fails, stop: do not repair the core guards here.
        assert after == snapshot == before, ("STOP: published content changed", method, path, body, status, response)
        if expected == "reject":
            assert 400 <= status < 500, (method, path, body, status, response)
        elif expected == "accept":
            assert 200 <= status < 300, (method, path, body, status, response)
        else:
            assert status in expected, (method, path, body, status, response)
        user_status = None
        if user_path is not None:
            reset_admission(monkeypatch, enabled)
            user_status, user_response, _ = request(method, user_path, user_body if user_body is not None else body)
            assert 200 <= user_status < 300, (method, user_path, user_body, user_status, user_response)
            assert digests(api) == before
        rows.append(dict(method=method, route=route, base_status=status, user_status=user_status, response=response))
        exercised.add((method, route))
        report(f"writes-{api.engine.dialect.name}-{enabled}-{package}", rows)

    for suffix, body in (("aliases", {"alias": "matrix-extra-alias"}),
                         ("notation", changed_notation),
                         ("latex-template", {"latex_template": "\\mathrm{matrix}"})):
        method = "POST" if suffix == "aliases" else "PATCH"
        check(method, "/symbols/{id}/" + suffix, f"/symbols/{ids['symbol']}/{suffix}", body,
              user_path=f"/symbols/{user_symbol['id']}/{suffix}")
    for kind, base_id, user in (("axioms", ids["axiom"], user_axiom), ("theorems", ids["theorem"], user_theorem)):
        check("PATCH", f"/{kind}/{{id}}/description", f"/{kind}/{base_id}/description", {"description": "matrix replacement"}, user_path=f"/{kind}/{user['id']}/description")
        check("POST", f"/{kind}/{{id}}/tags", f"/{kind}/{base_id}/tags", {"tag_id": fresh_tag["id"]}, user_path=f"/{kind}/{user['id']}/tags")
        check("DELETE", f"/{kind}/{{id}}/tags/{{tag_id}}", f"/{kind}/{base_id}/tags/{ids['tag']}", None, user_path=f"/{kind}/{user['id']}/tags/{fresh_tag['id']}")
    check("POST", "/axiom-systems/{id}/members", f"/axiom-systems/{ids['system']}/members", {"axiom_id": user_axiom["id"]}, user_path=f"/axiom-systems/{user_system['id']}/members")
    # Use an existing member so deletion actually attempts a change.
    accepted("POST", f"/axiom-systems/{user_system['id']}/members", {"axiom_id": ids["member"]})
    check("DELETE", "/axiom-systems/{id}/members/{axiom_id}", f"/axiom-systems/{ids['system']}/members/{ids['member']}", None, user_path=f"/axiom-systems/{user_system['id']}/members/{ids['member']}")
    check("POST", "/proofs", "/proofs", {"theorem_id": ids["theorem"]}, user_path="/proofs", user_body={"theorem_id": user_theorem["id"]})
    check("POST", "/proofs/{id}/steps", f"/proofs/{ids['proof']}/steps", {"kind": "axiom", "axiom_id": ids["axiom"]}, user_path=f"/proofs/{user_proof['id']}/steps")
    # Validating an already verified proof is an intentional, immutable no-op.
    check("POST", "/proofs/{id}/validate", f"/proofs/{ids['proof']}/validate", None, expected="accept")
    check("POST", "/formulas", "/formulas", {"tokens": tokens}, expected="accept")
    check("POST", "/formulas/validate", "/formulas/validate", {"tokens": tokens}, expected="accept")
    check("POST", "/formulas/search", "/formulas/search", {"pattern": "⊥"}, expected="accept")
    check("POST", "/proofs/compute-substituted-tokens", "/proofs/compute-substituted-tokens", {"formula_id": ids["formula"]}, expected="accept")
    assert free is not None
    check("POST", "/proofs/compute-gen-tokens", "/proofs/compute-gen-tokens", {"body_formula_id": ids["formula"], "gen_variable_symbol_id": free}, expected="accept")
    for suffix in ("suggest", "suggest-backward"):
        body = {"kind": "axiom", "axiom_id": ids["axiom"], "goal_tokens": tokens}
        check("POST", "/proofs/{id}/steps/" + suffix, f"/proofs/{ids['proof']}/steps/{suffix}", body, expected="accept")
    # Role assignment is global; use an existing schema-derived role to test
    # conflict in ordinary mode and explicit disablement in beta mode.
    with api.session() as dem:
        role = dem.session.execute(select(Base.metadata.tables["symbol_role"])).mappings().first()
    check("POST", "/symbol-roles", "/symbol-roles", {"role": role["role"], "symbol_id": role["symbol_id"]})
    reset_admission(monkeypatch, enabled)
    exploration = accepted("POST", "/explorations", {"name": "matrix-exploration", "premise_formula_ids": [ids["formula"]]})
    proof_id = exploration["proof"]["id"]
    accepted("POST", f"/proofs/{proof_id}/steps", {"kind": "premise", "premise_ord": 0})
    check("POST", "/explorations/{ref}/steps/{step_ord}/promote", f"/explorations/{ids['theorem']}/steps/0/promote", {"name": "matrix-promoted"}, user_path=f"/explorations/{exploration['theorem']['id']}/steps/0/promote")
    exercised.add(("POST", "/explorations"))
    assert exercised == PROTECTED | USER_OR_COMPUTATION
    assert digests(api) == before
