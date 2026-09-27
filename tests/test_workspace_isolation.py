"""Phase 3.5 workspace routing and management-database contracts."""

from __future__ import annotations

import asyncio
import io
import json
import shutil
import sqlite3
import zipfile
from statistics import median
from time import perf_counter
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import Session
from starlette.requests import Request

from dem.api import DemApi
from dem.types import SymbolTypeName, Token
from scripts.build_workspace_template import build_workspace_template
from webapi.deps import (
    DEVELOPMENT_ACCOUNT_ID,
    RequestAccount,
    WorkspaceApiCache,
    close_database_connections,
    get_dem_api,
    initialize_on_startup,
)
from webapi.main import app
from webapi.management.database import (
    create_management_engine,
    upgrade_management_schema,
)
from webapi.management.models import Account, Workspace
from webapi.management.workspace import (
    create_workspace_from_template,
    production_fingerprint,
    template_fingerprint_path,
    validate_workspace_template,
)
from webapi.management.schema_revision import (
    content_schema_head,
    stamp_content_schema,
    upgrade_content_schema,
)


EXPECTED_MANAGEMENT_COLUMNS = {
    "account": {"id", "external_subject", "email", "display_name", "created_at"},
    "workspace": {
        "id",
        "account_id",
        "slug",
        "title",
        "visibility",
        "storage_uri",
        "template_fingerprint",
        "schema_revision",
        "schema_state",
        "schema_error",
        "schema_checked_at",
        "created_at",
    },
    "workspace_member": {"workspace_id", "account_id", "role"},
}


def _sqlite_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.as_posix()}"


def _request(workspace_id: UUID) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/theorems",
            "headers": [(b"x-workspace-id", str(workspace_id).encode())],
        }
    )


def _http_get(path: str, workspace_id: UUID | None = None) -> tuple[int, bytes]:
    async def send_request() -> tuple[int, bytes]:
        headers = [(b"host", b"test")]
        if workspace_id is not None:
            headers.append((b"x-workspace-id", str(workspace_id).encode()))
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "root_path": "",
            "query_string": b"",
            "headers": headers,
            "server": ("test", 80),
            "client": ("test", 1234),
        }
        messages: list[dict[str, object]] = []
        received = False

        async def receive() -> dict[str, object]:
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

        async def send(message: dict[str, object]) -> None:
            messages.append(message)

        await asyncio.wait_for(app(scope, receive, send), timeout=10)
        start = next(m for m in messages if m["type"] == "http.response.start")
        body = b"".join(
            m.get("body", b"")
            for m in messages
            if m["type"] == "http.response.body"
        )
        return int(start["status"]), body

    return asyncio.run(send_request())


def _http_json(
    method: str,
    path: str,
    workspace_id: UUID,
    payload: dict[str, object] | None = None,
) -> tuple[int, object]:
    async def send_request() -> tuple[int, object]:
        body = json.dumps(payload).encode() if payload is not None else b""
        headers = [
            (b"host", b"test"),
            (b"x-workspace-id", str(workspace_id).encode()),
        ]
        if payload is not None:
            headers.append((b"content-type", b"application/json"))
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
            "headers": headers,
            "server": ("test", 80),
            "client": ("test", 1234),
        }
        messages: list[dict[str, object]] = []
        delivered = False

        async def receive() -> dict[str, object]:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

        async def send(message: dict[str, object]) -> None:
            messages.append(message)

        await asyncio.wait_for(app(scope, receive, send), timeout=10)
        start = next(m for m in messages if m["type"] == "http.response.start")
        response_body = b"".join(
            m.get("body", b"")
            for m in messages
            if m["type"] == "http.response.body"
        )
        return int(start["status"]), json.loads(response_body)

    return asyncio.run(send_request())


def _provision_minimal_workspace(database_url: str) -> None:
    api = DemApi.from_url(database_url)
    try:
        api.create_schema()
        api.seed_core(include_inference_rules=False, include_hilbert_core=False)
    finally:
        api.engine.dispose()
    stamp_content_schema(database_url, content_schema_head())


@pytest.fixture(autouse=True)
def isolated_dependency_state(monkeypatch):
    close_database_connections()
    monkeypatch.delenv("DEM_MANAGEMENT_DATABASE_URL", raising=False)
    monkeypatch.delenv("DEM_DATABASE_URL", raising=False)
    monkeypatch.delenv("DEM_WORKSPACE_TEMPLATE_PATH", raising=False)
    yield
    close_database_connections()


@pytest.fixture(scope="module")
def workspace_template(tmp_path_factory) -> Path:
    template_path = tmp_path_factory.mktemp("workspace-template") / "template.db"
    build_workspace_template(template_path)
    return template_path


@pytest.fixture(scope="module")
def provisioned_workspaces(tmp_path_factory):
    workspace_dir = tmp_path_factory.mktemp("workspace-isolation")
    management_url = _sqlite_url(workspace_dir / "management.db")
    alpha_id, beta_id, foreign_id = uuid4(), uuid4(), uuid4()
    alpha_url = _sqlite_url(workspace_dir / "alpha.db")
    beta_url = _sqlite_url(workspace_dir / "beta.db")
    foreign_url = _sqlite_url(workspace_dir / "foreign.db")
    for database_url in (alpha_url, beta_url, foreign_url):
        _provision_minimal_workspace(database_url)

    upgrade_management_schema(management_url)
    engine = create_management_engine(management_url)
    other_account_id = uuid4()
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                Account(
                    id=DEVELOPMENT_ACCOUNT_ID,
                    external_subject="development:single-account",
                    email=None,
                    display_name="Development account",
                ),
                Account(
                    id=other_account_id,
                    external_subject="development:other-account",
                    email=None,
                    display_name="Other account",
                ),
            ]
        )
        session.add_all(
            [
                Workspace(
                    id=alpha_id,
                    account_id=DEVELOPMENT_ACCOUNT_ID,
                    slug="alpha",
                    title="Alpha",
                    visibility="public",
                    storage_uri=alpha_url,
                    schema_revision=content_schema_head(),
                    schema_state="ready",
                ),
                Workspace(
                    id=beta_id,
                    account_id=DEVELOPMENT_ACCOUNT_ID,
                    slug="beta",
                    title="Beta",
                    visibility="public",
                    storage_uri=beta_url,
                    schema_revision=content_schema_head(),
                    schema_state="ready",
                ),
                Workspace(
                    id=foreign_id,
                    account_id=other_account_id,
                    slug="foreign",
                    title="Foreign",
                    visibility="public",
                    storage_uri=foreign_url,
                    schema_revision=content_schema_head(),
                    schema_state="ready",
                ),
            ]
        )
    engine.dispose()
    return management_url, alpha_id, beta_id, foreign_id


@pytest.fixture
def managed_workspaces(provisioned_workspaces, monkeypatch):
    management_url, alpha_id, beta_id, foreign_id = provisioned_workspaces
    monkeypatch.setenv("DEM_MANAGEMENT_DATABASE_URL", management_url)
    return alpha_id, beta_id, foreign_id


def test_management_schema_has_exact_required_tables_and_columns(tmp_path: Path):
    database_url = _sqlite_url(tmp_path / "management.db")

    upgrade_management_schema(database_url)

    engine = create_management_engine(database_url)
    try:
        inspector = inspect(engine)
        business_tables = set(inspector.get_table_names()) - {"alembic_version"}
        assert business_tables == set(EXPECTED_MANAGEMENT_COLUMNS)
        for table, expected_columns in EXPECTED_MANAGEMENT_COLUMNS.items():
            assert {column["name"] for column in inspector.get_columns(table)} == expected_columns
    finally:
        engine.dispose()


def test_workspace_template_fingerprint_matches_production_implementation(
    workspace_template: Path,
):
    assert (
        template_fingerprint_path(workspace_template).read_text(encoding="ascii").strip()
        == production_fingerprint()
    )


def test_workspace_template_validation_releases_sqlite_connection(
    tmp_path: Path, workspace_template: Path,
):
    copied = tmp_path / "validated-template.db"
    moved = tmp_path / "moved-template.db"
    shutil.copy2(workspace_template, copied)
    shutil.copy2(
        template_fingerprint_path(workspace_template),
        template_fingerprint_path(copied),
    )

    validate_workspace_template(copied)

    copied.replace(moved)
    assert moved.is_file()


def test_workspace_template_is_the_documented_public_layer(workspace_template: Path):
    with sqlite3.connect(workspace_template) as connection:
        counts = {
            table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("symbol", "formula", "theorem", "proof")
        }
        verified = connection.execute(
            "SELECT count(*) FROM proof WHERE status = 'verified'"
        ).fetchone()[0]
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]

    assert counts == {"symbol": 17, "formula": 8, "theorem": 0, "proof": 0}
    assert verified == 0
    assert revision == content_schema_head()


def test_workspace_template_without_embedded_revision_is_rejected(
    tmp_path: Path, workspace_template: Path
):
    versionless = tmp_path / "versionless.db"
    shutil.copy2(workspace_template, versionless)
    shutil.copy2(
        template_fingerprint_path(workspace_template),
        template_fingerprint_path(versionless),
    )
    with sqlite3.connect(versionless) as connection:
        connection.execute("DROP TABLE alembic_version")

    with pytest.raises(RuntimeError, match="no embedded Alembic revision"):
        validate_workspace_template(versionless)


def test_management_startup_rejects_stale_workspace_template(
    tmp_path: Path, workspace_template: Path, monkeypatch
):
    stale_template = tmp_path / "stale-template.db"
    shutil.copy2(workspace_template, stale_template)
    template_fingerprint_path(stale_template).write_text("stale\n", encoding="ascii")
    monkeypatch.setenv(
        "DEM_MANAGEMENT_DATABASE_URL", _sqlite_url(tmp_path / "management.db")
    )
    monkeypatch.setenv("DEM_WORKSPACE_TEMPLATE_PATH", str(stale_template))

    with pytest.raises(RuntimeError, match="does not match production code"):
        initialize_on_startup()


def test_workspace_creation_by_template_copy_is_under_one_second(
    tmp_path: Path, workspace_template: Path, capsys
):
    management_url = _sqlite_url(tmp_path / "management.db")
    upgrade_management_schema(management_url)
    engine = create_management_engine(management_url)
    samples: list[float] = []
    try:
        with Session(engine) as session, session.begin():
            session.add(
                Account(
                    id=DEVELOPMENT_ACCOUNT_ID,
                    external_subject="development:single-account",
                    email=None,
                    display_name="Development account",
                )
            )
        for index in range(3):
            started = perf_counter()
            with Session(engine) as session, session.begin():
                create_workspace_from_template(
                    session,
                    account_id=DEVELOPMENT_ACCOUNT_ID,
                    slug=f"timed-{index}",
                    title=f"Timed {index}",
                    template_path=workspace_template,
                    workspace_path=tmp_path / f"timed-{index}.db",
                )
            samples.append(perf_counter() - started)
    finally:
        engine.dispose()

    measured = median(samples)
    with capsys.disabled():
        print(
            "\nworkspace template-copy creation times: "
            f"{', '.join(f'{sample:.3f}s' for sample in samples)}; "
            f"median {measured:.3f}s"
        )
    assert measured < 1.0


def test_copied_workspace_supports_http_authoring_and_verified_proof(
    tmp_path: Path, workspace_template: Path, monkeypatch
):
    management_url = _sqlite_url(tmp_path / "management.db")
    monkeypatch.setenv("DEM_MANAGEMENT_DATABASE_URL", management_url)
    monkeypatch.setenv("DEM_WORKSPACE_TEMPLATE_PATH", str(workspace_template))
    initialize_on_startup()

    engine = create_management_engine(management_url)
    try:
        with Session(engine) as session, session.begin():
            workspace = create_workspace_from_template(
                session,
                account_id=DEVELOPMENT_ACCOUNT_ID,
                slug="authoring",
                title="Authoring",
                template_path=workspace_template,
                workspace_path=tmp_path / "authoring.db",
            )
            workspace_id = workspace.id
    finally:
        engine.dispose()

    status, symbol_types = _http_json("GET", "/symbol-types", workspace_id)
    assert status == 200
    prop_type_id = next(
        row["id"] for row in symbol_types if row["name"] == SymbolTypeName.FREE_PROP_VAR.value
    )
    status, proposition = _http_json(
        "POST",
        "/symbols",
        workspace_id,
        {"name": "phase36_proposition", "symbol_type_id": prop_type_id, "arity": 0},
    )
    assert status == 201
    status, implication = _http_json(
        "GET", "/symbol-roles/implication", workspace_id
    )
    assert status == 200

    status, atom = _http_json(
        "POST",
        "/formulas",
        workspace_id,
        {"tokens": [{"symbol_id": proposition["id"]}]},
    )
    assert status == 201
    status, statement = _http_json(
        "POST",
        "/formulas",
        workspace_id,
        {
            "tokens": [
                {"symbol_id": implication["id"]},
                {"symbol_id": proposition["id"]},
                {"symbol_id": proposition["id"]},
            ]
        },
    )
    assert status == 201
    status, theorem = _http_json(
        "POST",
        "/theorems",
        workspace_id,
        {"name": "phase36_self_implication", "conclusion_formula_id": statement["id"]},
    )
    assert status == 201
    status, proof = _http_json(
        "POST", "/proofs", workspace_id, {"theorem_id": theorem["id"]}
    )
    assert status == 201
    status, _ = _http_json(
        "POST",
        f"/proofs/{proof['id']}/steps",
        workspace_id,
        {"kind": "assumption", "conclusion_formula_id": atom["id"]},
    )
    assert status == 201
    status, _ = _http_json(
        "POST",
        f"/proofs/{proof['id']}/steps",
        workspace_id,
        {
            "kind": "imp_intro",
            "conclusion_formula_id": statement["id"],
            "assumption_step_ord": 0,
            "body_step_ord": 0,
        },
    )
    assert status == 201
    status, result = _http_json(
        "POST", f"/proofs/{proof['id']}/validate", workspace_id, {}
    )
    assert status == 200
    assert result == {"status": "verified"}


def test_workspace_content_is_structurally_isolated(managed_workspaces):
    alpha_id, beta_id, _ = managed_workspaces
    account = RequestAccount(DEVELOPMENT_ACCOUNT_ID)
    alpha_api = get_dem_api(_request(alpha_id), account)
    with alpha_api.transaction() as dem:
        prop_type = dem.symbols.get_symbol_type_by_name(
            SymbolTypeName.FREE_PROP_VAR.value
        )
        symbol = dem.symbols.register("alpha_only_proposition", prop_type.id, 0)
        formula = dem.formulas.register([Token(symbol_id=symbol.id)])
        dem.theorems.register("alpha_only_theorem", formula.id)

    alpha_status, alpha_body = _http_get("/theorems", alpha_id)
    beta_status, beta_body = _http_get("/theorems", beta_id)

    assert alpha_status == beta_status == 200
    assert "alpha_only_theorem" in {row["name"] for row in json.loads(alpha_body)}
    assert "alpha_only_theorem" not in {row["name"] for row in json.loads(beta_body)}


def test_session_and_engine_never_span_workspaces(managed_workspaces):
    alpha_id, beta_id, _ = managed_workspaces
    account = RequestAccount(DEVELOPMENT_ACCOUNT_ID)

    alpha_api = get_dem_api(_request(alpha_id), account)
    beta_api = get_dem_api(_request(beta_id), account)

    assert alpha_api is not beta_api
    assert alpha_api.engine is not beta_api.engine
    with alpha_api.session() as alpha, beta_api.session() as beta:
        assert alpha.session.get_bind() is alpha_api.engine
        assert beta.session.get_bind() is beta_api.engine
        assert alpha.session.get_bind() is not beta.session.get_bind()


def test_unknown_and_foreign_workspace_requests_are_indistinguishable(
    managed_workspaces,
):
    _, _, foreign_id = managed_workspaces

    foreign_response = _http_get("/theorems", foreign_id)
    missing_response = _http_get("/theorems", uuid4())

    assert foreign_response == missing_response
    assert foreign_response == (404, b'{"detail":"Workspace not found"}')


def test_workspace_export_is_available(managed_workspaces):
    alpha_id, _, _ = managed_workspaces

    status, body = _http_get("/workspace/export", alpha_id)

    assert status == 200
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["package"] == "workspace.alpha"
        assert manifest["version"] == "0.0.0"
        assert manifest["dem_runtime"]
        assert manifest["description"] == "Workspace export: Alpha"
        assert set(manifest["empty_field_reasons"]) == {"depends", "license"}


def test_foreign_workspace_export_is_indistinguishable_from_missing_workspace(
    managed_workspaces,
):
    _, _, foreign_id = managed_workspaces

    foreign_response = _http_get("/workspace/export", foreign_id)
    missing_response = _http_get("/workspace/export", uuid4())

    assert foreign_response == missing_response
    assert foreign_response == (404, b'{"detail":"Workspace not found"}')


def test_workspace_engine_cache_is_bounded_lru():
    cache = WorkspaceApiCache(max_size=2)
    try:
        first = cache.get("first", "sqlite+pysqlite:///:memory:")
        second = cache.get("second", "sqlite+pysqlite:///:memory:")
        assert cache.get("first", "sqlite+pysqlite:///:memory:") is first
        cache.get("third", "sqlite+pysqlite:///:memory:")

        assert len(cache) == 2
        assert cache.get("second", "sqlite+pysqlite:///:memory:") is not second
        assert len(cache) == 2
    finally:
        cache.close()


def test_legacy_single_database_deployment_without_management_db(
    tmp_path: Path, monkeypatch
):
    database_url = _sqlite_url(tmp_path / "legacy.db")
    monkeypatch.setenv("DEM_DATABASE_URL", database_url)

    initialize_on_startup()
    status, body = _http_get("/symbols")

    assert status == 200
    assert json.loads(body)
    engine = get_dem_api(
        Request({"type": "http", "method": "GET", "path": "/", "headers": []}),
        RequestAccount(DEVELOPMENT_ACCOUNT_ID),
    ).engine
    assert str(engine.url) == database_url
