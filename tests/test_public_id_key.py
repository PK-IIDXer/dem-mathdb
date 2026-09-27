"""The explicit birth-key path for public IDs (N11-C stage A, lean-import-design §5.2 B).

A public ID is fixed when a row is created.  Foundation data that places an
entity in a namespace other than the one it was born in names the birth key
(``<namespace>::<name>``) explicitly; the REST API can never do so.
"""

from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from dem.api import DemApi, DemServices
from dem.db.models import Base
from dem.db.seed import seed_language
from dem.errors import ConflictError, ValidationError
from dem.identity import deterministic_public_id, public_id_from_key
from dem.services.definition import DefinitionPublicIdKeys
from dem.types import LogicalDefinitionInput, SymbolTypeName, Token
from webapi.deps import dem_services
from webapi.main import app

REPO_ROOT = Path(__file__).resolve().parents[1]
BIRTH = "dem.foundation.logic"
MOVED = "local.moved"


@pytest.fixture
def dem():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_language(session)
        yield DemServices(session)
    engine.dispose()


def _prop_type(dem: DemServices) -> int:
    return dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value).id


def test_birth_key_keeps_the_public_id_of_a_moved_symbol(dem: DemServices) -> None:
    symbol = dem.symbols.register(
        "moved", _prop_type(dem), 0, namespace=MOVED, public_id_key=f"{BIRTH}::moved"
    )
    assert symbol.namespace.name == MOVED
    assert symbol.public_id == deterministic_public_id("symbol", f"{BIRTH}::moved")
    assert symbol.public_id != deterministic_public_id("symbol", f"{MOVED}::moved")
    # Without a key, the ID still comes from where the row is created.
    plain = dem.symbols.register("plain", _prop_type(dem), 0, namespace=MOVED)
    assert plain.public_id == deterministic_public_id("symbol", f"{MOVED}::plain")


def test_birth_key_keeps_theorem_axiom_and_definition_ids(dem: DemServices) -> None:
    phi = dem.symbols.register("φ", _prop_type(dem), 0)
    formula = dem.formulas.register([Token(symbol_id=phi.id)])

    theorem = dem.theorems.register(
        "moved theorem", formula.id, namespace=MOVED, public_id_key=f"{BIRTH}::moved theorem"
    )
    assert theorem.namespace.name == MOVED
    assert theorem.public_id == deterministic_public_id("theorem", f"{BIRTH}::moved theorem")

    axiom = dem.axioms.register(
        "moved axiom", formula.id, namespace=MOVED, public_id_key=f"{BIRTH}::moved axiom"
    )
    assert axiom.namespace.name == MOVED
    assert axiom.public_id == deterministic_public_id("axiom", f"{BIRTH}::moved axiom")
    assert dem.axioms.register("plain axiom", formula.id).namespace.name == BIRTH

    keys = DefinitionPublicIdKeys(
        symbol=f"{BIRTH}::Moved", definition=f"{BIRTH}::Moved", axiom=f"{BIRTH}::Moved 定義公理"
    )
    definition = dem.definitions.register(
        LogicalDefinitionInput(name="Moved", param_symbol_ids=(phi.id,), body_formula_id=formula.id),
        namespace=MOVED,
        public_id_keys=keys,
    )
    assert definition.new_symbol.namespace.name == MOVED
    assert definition.new_symbol.public_id == deterministic_public_id("symbol", keys.symbol)
    assert definition.public_id == deterministic_public_id("definition", keys.definition)
    defining_axiom = next(a for a in dem.axioms.list_axioms() if a.definition_id == definition.id)
    assert defining_axiom.public_id == deterministic_public_id("axiom", keys.axiom)
    assert defining_axiom.namespace.name == MOVED


@pytest.mark.parametrize(
    "key",
    ["moved", "::moved", f"{BIRTH}::", f"{BIRTH}:: moved", "Bad.Namespace::moved", "single::moved"],
)
def test_malformed_birth_keys_are_rejected(dem: DemServices, key: str) -> None:
    with pytest.raises(ValueError):
        public_id_from_key("symbol", key)
    with pytest.raises(ValidationError) as caught:
        dem.symbols.register("moved", _prop_type(dem), 0, namespace=MOVED, public_id_key=key)
    assert caught.value.code == "identity.invalid_public_id_key"


def test_a_birth_key_cannot_take_an_existing_identity(dem: DemServices) -> None:
    kind = _prop_type(dem)
    dem.symbols.register("taken", kind, 0, namespace=BIRTH)
    with pytest.raises(ConflictError) as symbol_conflict:
        dem.symbols.register("other", kind, 0, namespace=MOVED, public_id_key=f"{BIRTH}::taken")
    assert symbol_conflict.value.field == "public_id"

    phi = dem.symbols.register("φ", kind, 0)
    formula = dem.formulas.register([Token(symbol_id=phi.id)])
    dem.theorems.register("taken", formula.id, namespace=BIRTH)
    with pytest.raises(ConflictError) as theorem_conflict:
        dem.theorems.register("other", formula.id, namespace=MOVED, public_id_key=f"{BIRTH}::taken")
    assert theorem_conflict.value.field == "public_id"
    dem.axioms.register("taken axiom", formula.id)
    with pytest.raises(ConflictError) as axiom_conflict:
        dem.axioms.register("other axiom", formula.id, public_id_key=f"{BIRTH}::taken axiom")
    assert axiom_conflict.value.field == "public_id"


# ---------------------------------------------------------------------------
# REST never reaches the explicit-key path


def test_webapi_and_the_dem_api_never_pass_a_birth_key() -> None:
    offenders = []
    for root in ("webapi", "dem/api"):
        for path in (REPO_ROOT / root).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.keyword) and node.arg in {"public_id_key", "public_id_keys"}:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
                if isinstance(node, ast.Name) and node.id in {"public_id_from_key", "DefinitionPublicIdKeys"}:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
    assert offenders == []


def test_request_schemas_have_no_birth_key_field() -> None:
    from webapi import schemas

    for name in ("SymbolCreate", "TheoremCreate", "AxiomCreate", "DefinitionCreate"):
        model = getattr(schemas, name)
        fields = set(model.model_fields) if hasattr(model, "model_fields") else set()
        assert not {"public_id_key", "public_id_keys", "public_id"} & fields, name


@pytest.fixture
def rest():
    api = DemApi.from_url(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    api.initialize_database(include_inference_rules=False, include_hilbert_core=False)
    with api.transaction() as dem:
        phi = dem.symbols.register("RestPhi", _prop_type(dem), 0)
        formula_id = dem.formulas.register([Token(symbol_id=phi.id)]).id

    previous = app.dependency_overrides.copy()

    def transactional_services():
        with api.transaction() as dem:
            yield dem

    app.dependency_overrides[dem_services] = transactional_services

    def post(path: str, body: dict[str, object]) -> tuple[int, dict[str, object]]:
        async def request() -> tuple[int, dict[str, object]]:
            payload = json.dumps(body).encode()
            scope = {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.4"},
                "http_version": "1.1",
                "method": "POST",
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
                    return {"type": "http.request", "body": payload, "more_body": False}
                await asyncio.Event().wait()

            async def send(message):
                messages.append(message)

            await asyncio.wait_for(app(scope, receive, send), timeout=30)
            start = next(item for item in messages if item["type"] == "http.response.start")
            body_bytes = b"".join(
                item.get("body", b"") for item in messages if item["type"] == "http.response.body"
            )
            return int(start["status"]), json.loads(body_bytes)

        return asyncio.run(request())

    try:
        yield api, formula_id, post
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        api.engine.dispose()


def test_a_rest_request_cannot_claim_a_birth_key(rest) -> None:
    api, formula_id, post = rest
    claimed = f"{BIRTH}::∧"
    with api.session() as dem:
        kind = _prop_type(dem)

    status, symbol = post(
        "/symbols",
        {"name": "RestClaim", "symbol_type_id": kind, "arity": 0, "public_id_key": claimed},
    )
    assert status == 201
    assert symbol["public_id"] == deterministic_public_id("symbol", f"{BIRTH}::RestClaim")
    assert symbol["public_id"] != deterministic_public_id("symbol", claimed)

    status, theorem = post(
        "/theorems",
        {"name": "RestClaim", "conclusion_formula_id": formula_id, "public_id_key": claimed},
    )
    assert status == 201
    assert theorem["public_id"] == deterministic_public_id("theorem", f"{BIRTH}::RestClaim")
