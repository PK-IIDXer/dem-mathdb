"""Real request transactions on disposable, verified seed snapshot copies."""
import asyncio
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine

from dem.api import DemApi
from scripts.beta_base import archive_digests, publish_all
from webapi import beta, deps
from webapi.main import app
from beta_http import asgi_request


def request(method, path, body=None):
    return asyncio.run(asgi_request(app, method, path, body, raise_app_exceptions=False))


def report(name, result):
    directory = os.environ.get("BETA2_REPORT_DIR")
    if directory:
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        (target / (name + ".json")).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture
def base_api(request, fresh_seeded_session, seed_snapshot_factory, monkeypatch):
    phase = getattr(request.module, "SEED_PHASE", None)
    if phase is None:
        from beta_fixture import base_phase
        phase = base_phase()
    bind = fresh_seeded_session.get_bind()
    engine = bind.engine if hasattr(bind, "engine") else bind
    own_engine = None
    if engine.dialect.name == "postgresql":
        factory = seed_snapshot_factory.postgresql
        name = factory._worker_database("beta2" + uuid4().hex[:12], factory.get(phase))
        own_engine = create_engine(engine.url.set(database=name))
        engine = own_engine
    api = DemApi(engine)
    context = deps.WorkspaceRequestContext(UUID(int=0), "test", None, "local.workspace", api)
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[deps.get_workspace_request_context] = lambda: context
    for variable in ("DEM_READ_ONLY", "DEM_BETA", "DEM_BETA_FLAG_DIR"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(beta, "runtime", beta.Runtime())
    monkeypatch.setattr(app.state, "beta_limits", beta.Limits(), raising=False)
    try:
        yield api
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        if own_engine is not None:
            own_engine.dispose()


@pytest.fixture
def published_api(base_api):
    publish_all(base_api.engine)
    return base_api


def digests(api):
    with api.session() as dem:
        return archive_digests(dem.session)
