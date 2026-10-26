from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy.orm import Session

from dem.api import DemServices
from dem.identity import DEFAULT_NAMESPACE_NAME
from dem.services.theorem import LemmaCandidate, rank_lemma_candidates
from dem.types import LogicalDefinitionInput, SymbolTypeName, Token
from webapi.deps import LOCAL_WORKSPACE_NAMESPACE, dem_services
from webapi.main import app


SEED_PHASE = "public_demo"
SEED_DATABASE = "sqlite"


@pytest.fixture
def local_namespace_api(fresh_seeded_session: Session):
    dem = DemServices(fresh_seeded_session)
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[dem_services] = lambda: dem

    def request(
        method: str,
        path: str,
        body: dict[str, object] | None = None,
    ) -> tuple[int, object]:
        async def run() -> tuple[int, object]:
            payload = json.dumps(body).encode() if body is not None else b""
            scope = {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.4"},
                "http_version": "1.1",
                "method": method,
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "root_path": "",
                "query_string": b"",
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
                    return {
                        "type": "http.request",
                        "body": payload,
                        "more_body": False,
                    }
                await asyncio.Event().wait()

            async def send(message):
                messages.append(message)

            await asyncio.wait_for(app(scope, receive, send), timeout=30)
            start = next(
                item for item in messages if item["type"] == "http.response.start"
            )
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


def _assert_ambiguous(request, path: str, code: str) -> None:
    status, body = request("GET", path)
    assert status == 422
    assert body["code"] == code


def test_api_authored_entities_use_the_local_namespace_and_qualified_lookup(
    local_namespace_api,
) -> None:
    dem, request = local_namespace_api
    seed_phi = dem.symbols.get_by_name("φ", namespace=DEFAULT_NAMESPACE_NAME)
    proposition = dem.formulas.register([Token(symbol_id=seed_phi.id)])
    dem.definitions.register(
        LogicalDefinitionInput(
            name="DuplicateDefinition",
            param_symbol_ids=(seed_phi.id,),
            body_formula_id=proposition.id,
        )
    )

    status, definition = request(
        "POST",
        "/definitions",
        {
            "kind": "logical",
            "name": "DuplicateDefinition",
            "param_symbol_ids": [seed_phi.id],
            "body_formula_id": proposition.id,
        },
    )
    assert status == 201, definition
    local_definition = dem.definitions.get(definition["id"])
    assert local_definition.new_symbol.namespace.name == LOCAL_WORKSPACE_NAMESPACE
    assert (
        dem.definitions.get_axiom(local_definition.id).namespace.name
        == LOCAL_WORKSPACE_NAMESPACE
    )

    prop_type = dem.symbols.get_symbol_type_by_name(
        SymbolTypeName.FREE_PROP_VAR.value
    )
    status, symbol = request(
        "POST",
        "/symbols",
        {"name": "φ", "symbol_type_id": prop_type.id, "arity": 0},
    )
    assert status == 201, symbol
    local_formula = dem.formulas.register([Token(symbol_id=symbol["id"])])

    status, axiom = request(
        "POST",
        "/axioms",
        {"name": "hilbert_k", "formula_id": local_formula.id},
    )
    assert status == 201, axiom
    status, system = request(
        "POST", "/axiom-systems", {"name": "Local system"}
    )
    assert status == 201, system

    seed_theorem = dem.theorems.get_by_name(
        "含意の自己適用", namespace=DEFAULT_NAMESPACE_NAME
    )
    status, theorem = request(
        "POST",
        "/theorems",
        {
            "name": "含意の自己適用",
            "conclusion_formula_id": local_formula.id,
        },
    )
    assert status == 201, theorem
    assert theorem["public_id"] != seed_theorem.public_id

    status, note = request(
        "POST",
        "/explorations",
        {"name": "local-note", "premise_formula_ids": [local_formula.id]},
    )
    assert status == 201, note
    status, step = request(
        "POST",
        f"/proofs/{note['proof']['id']}/steps",
        {
            "kind": "premise",
            "premise_ord": 0,
            "conclusion_formula_id": local_formula.id,
        },
    )
    assert status == 201, step
    status, promoted = request(
        "POST",
        f"/explorations/{note['theorem']['id']}/steps/{step['ord']}/promote",
        {"name": "local-promoted"},
    )
    assert status == 201, promoted

    for entity in (
        symbol,
        definition,
        axiom,
        system,
        theorem,
        note["theorem"],
        promoted["theorem"],
    ):
        assert entity["namespace_name"] == LOCAL_WORKSPACE_NAMESPACE

    _assert_ambiguous(request, "/symbols/by-name/φ", "symbol.ambiguous_name")
    _assert_ambiguous(
        request,
        "/definitions/by-name/DuplicateDefinition",
        "definition.ambiguous_name",
    )
    _assert_ambiguous(request, "/axioms/by-name/hilbert_k", "axiom.ambiguous_name")
    _assert_ambiguous(
        request,
        "/theorems/by-name/含意の自己適用",
        "theorem.ambiguous_name",
    )

    qualified = {
        "/symbols/by-name/local.workspace::φ": symbol["id"],
        "/definitions/by-name/local.workspace::DuplicateDefinition": definition["id"],
        "/axioms/by-name/local.workspace::hilbert_k": axiom["id"],
        "/theorems/by-name/local.workspace::含意の自己適用": theorem["id"],
    }
    for path, expected_id in qualified.items():
        status, entity = request("GET", path)
        assert status == 200, entity
        assert entity["id"] == expected_id

    assert dem.symbols.get_by_name(
        "φ", namespace=DEFAULT_NAMESPACE_NAME
    ).namespace.name == DEFAULT_NAMESPACE_NAME
    assert dem.axioms.get_by_name(
        "hilbert_k", namespace=DEFAULT_NAMESPACE_NAME
    ).namespace.name == DEFAULT_NAMESPACE_NAME
    assert dem.theorems.get_by_name(
        "含意の自己適用", namespace=DEFAULT_NAMESPACE_NAME
    ).namespace.name == DEFAULT_NAMESPACE_NAME
    assert dem.definitions.get_by_name(
        "DuplicateDefinition", namespace=DEFAULT_NAMESPACE_NAME
    ).namespace.name == DEFAULT_NAMESPACE_NAME


def test_local_namespace_is_not_a_shared_foundation_namespace(
    local_namespace_api,
) -> None:
    dem, _ = local_namespace_api
    prop_type = dem.symbols.get_symbol_type_by_name(
        SymbolTypeName.FREE_PROP_VAR.value
    )
    symbol = dem.symbols.register(
        "ranking-local", prop_type.id, 0, namespace=LOCAL_WORKSPACE_NAMESPACE
    )
    formula = dem.formulas.register([Token(symbol_id=symbol.id)])
    theorem = dem.theorems.register(
        "ranking-local", formula.id, namespace=LOCAL_WORKSPACE_NAMESPACE
    )

    shared = dem.theorems._shared_namespace_ids()
    assert theorem.namespace_id not in shared
    assert dem.symbols.get_by_name(
        "φ", namespace=DEFAULT_NAMESPACE_NAME
    ).namespace_id in shared

    tokens = (Token(symbol_id=symbol.id),)
    candidate = LemmaCandidate(
        theorem_id=theorem.id,
        conclusion_tokens=tokens,
        premise_tokens=(),
        usage_count=0,
        is_schematic=True,
        namespace_id=theorem.namespace_id,
    )
    symbol_meta = dem.formulas._load_symbol_meta(tokens)
    baseline = rank_lemma_candidates(
        [candidate], goal_tokens=tokens, symbol_meta=symbol_meta
    )[0]
    shared_only = rank_lemma_candidates(
        [candidate],
        goal_tokens=tokens,
        symbol_meta=symbol_meta,
        shared_namespace_ids=shared,
    )[0]
    current = rank_lemma_candidates(
        [candidate],
        goal_tokens=tokens,
        symbol_meta=symbol_meta,
        current_namespace_id=theorem.namespace_id,
        shared_namespace_ids=shared,
    )[0]
    assert shared_only.score == baseline.score
    assert current.score == baseline.score + 1.0
