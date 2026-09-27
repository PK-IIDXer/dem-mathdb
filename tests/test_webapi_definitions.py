"""HTTP contracts for atomic definition and symbol registration."""

from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.pool import StaticPool

from dem.api import DemApi
from dem.db.models.definition import Definition
from dem.db.models.language import Symbol
from dem.errors import NotFoundError
from dem.types import SymbolTypeName, Token
from webapi.deps import dem_services
from webapi.main import app


@pytest.fixture
def definition_api():
    api = DemApi.from_url(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    api.initialize_database(
        include_inference_rules=False,
        include_hilbert_core=False,
    )
    with api.transaction() as dem:
        prop_type = dem.symbols.get_symbol_type_by_name(
            SymbolTypeName.FREE_PROP_VAR.value
        )
        phi = dem.symbols.register("DefinitionEndpointPhi", prop_type.id, 0)
        body = dem.formulas.register([Token(symbol_id=phi.id)])
        param_id = phi.id
        body_id = body.id

    previous = app.dependency_overrides.copy()

    def transactional_services():
        with api.transaction() as dem:
            yield dem

    app.dependency_overrides[dem_services] = transactional_services

    def post(body: dict[str, object]) -> tuple[int, dict[str, object]]:
        async def request() -> tuple[int, dict[str, object]]:
            payload = json.dumps(body).encode()
            scope = {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.4"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": "/definitions",
                "raw_path": b"/definitions",
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
            start = next(
                item for item in messages if item["type"] == "http.response.start"
            )
            response_body = b"".join(
                item.get("body", b"")
                for item in messages
                if item["type"] == "http.response.body"
            )
            return int(start["status"]), json.loads(response_body)

        return asyncio.run(request())

    try:
        yield api, param_id, body_id, post
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        api.engine.dispose()


def definition_payload(name: str, param_id: int, body_id: int) -> dict[str, object]:
    return {
        "kind": "logical",
        "name": name,
        "param_symbol_ids": [param_id],
        "body_formula_id": body_id,
    }


def test_definition_endpoint_saves_normalized_template_in_same_request(
    definition_api,
) -> None:
    api, param_id, body_id, post = definition_api
    payload = definition_payload("EndpointTemplate", param_id, body_id)
    payload["latex_template"] = r"  \mathsf{EndpointTemplate}  "

    status, response = post(payload)

    assert status == 201
    with api.session() as dem:
        definition = dem.definitions.get_by_public_id(str(response["public_id"]))
        assert definition.new_symbol.latex_template == r"\mathsf{EndpointTemplate}"


@pytest.mark.parametrize("template", [None, "   "])
def test_definition_endpoint_keeps_name_fallback_for_empty_template(
    definition_api, template: str | None
) -> None:
    api, param_id, body_id, post = definition_api
    name = "OmittedTemplate" if template is None else "WhitespaceTemplate"
    payload = definition_payload(name, param_id, body_id)
    if template is not None:
        payload["latex_template"] = template

    status, _response = post(payload)

    assert status == 201
    with api.session() as dem:
        assert dem.definitions.get_by_name(name).new_symbol.latex_template is None


def test_definition_endpoint_rejects_template_over_1000_characters(
    definition_api,
) -> None:
    api, param_id, body_id, post = definition_api
    payload = definition_payload("TooLongTemplate", param_id, body_id)
    payload["latex_template"] = "x" * 1001
    with api.session() as dem:
        before = {
            model: dem.session.scalar(select(func.count()).select_from(model))
            for model in (Symbol, Definition)
        }

    status, _response = post(payload)

    assert status == 422
    with api.session() as dem:
        after = {
            model: dem.session.scalar(select(func.count()).select_from(model))
            for model in (Symbol, Definition)
        }
        assert after == before
        with pytest.raises(NotFoundError):
            dem.symbols.get_by_name("TooLongTemplate")
