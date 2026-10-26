"""Capture production FastAPI GET bodies verbatim for the Public build.

No response schemas or proof/validation logic are duplicated here. The caller
owns a read-only snapshot transaction; requests run serially on that snapshot.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
import gzip
from hashlib import sha256
import io
import json
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from dem.api import DemServices
from dem.db.models.theorem import Proof, Theorem
from dem.services.system_tags import visible_theorem_clause
from webapi.deps import dem_services
from webapi.main import app
from webapi.routers.formulas import BATCH_MAX_IDS

COMMON_PATHS = ("/config", "/symbols", "/tags", "/axiom-systems")


def initial_comparison_systems(systems: list[dict]) -> list[dict]:
    # ExternalChecksPanel's rule (frontend/src/externalChecks.ts) over the same
    # captured /axiom-systems body: the seed data's comparison_rank chooses the
    # systems, so neither side names one.
    return sorted((s for s in systems if s["comparison_rank"] is not None),
                  key=lambda s: s["comparison_rank"])


@contextmanager
def public_api(session: Session):
    """Use the real app without its database-initializing lifespan.

    This is an offline build context, not a live-server context. Only the DB
    dependency is replaced; handlers, response models and serialization run.
    """
    previous = app.dependency_overrides.copy()
    old_mode = os.environ.get("DEM_READ_ONLY")

    async def services():
        return DemServices(session)

    app.dependency_overrides[dem_services] = services
    os.environ["DEM_READ_ONLY"] = "true"
    try:
        yield app
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        if old_mode is None:
            os.environ.pop("DEM_READ_ONLY", None)
        else:
            os.environ["DEM_READ_ONLY"] = old_mode


async def get_body(application, path: str) -> bytes:
    route, _, query = path.partition("?")
    messages = []
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.Event().wait()

    async def send(message):
        messages.append(message)

    await application({
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1", "method": "GET", "scheme": "http",
        "path": route, "raw_path": route.encode(), "query_string": query.encode(),
        "root_path": "", "headers": [(b"host", b"public-build"), (b"accept-encoding", b"identity")],
        "server": ("public-build", 80), "client": ("127.0.0.1", 1),
    }, receive, send)
    start = next(m for m in messages if m["type"] == "http.response.start")
    headers = dict(start["headers"])
    if start["status"] != 200 or not headers.get(b"content-type", b"").startswith(b"application/json"):
        raise RuntimeError(f"Cannot snapshot {path}: HTTP {start['status']}")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    json.loads(body)  # Fail the build if the server did not produce valid JSON.
    return body


def response_map(responses: dict[str, bytes]) -> bytes:
    # Embed the original bytes, including key order/float/Unicode spelling.
    return b"{" + b",".join(json.dumps(k).encode() + b":" + responses[k]
                            for k in sorted(responses)) + b"}"


async def capture_data(session: Session, application,
                       proof_ids: set[str] | None = None) -> dict[str, bytes]:
    files = {}
    common = {path: await get_body(application, path) for path in COMMON_PATHS}
    files["common.json"] = response_map(common)
    systems = json.loads(common["/axiom-systems"])
    proofs = session.execute(select(Proof.id, Proof.public_id, Theorem.public_id.label("theorem_public_id"))
                             .join(Theorem, Theorem.id == Proof.theorem_id)
                             .where(visible_theorem_clause(Theorem.id)).order_by(Proof.public_id)).all()
    if proof_ids is not None and proof_ids - {p.public_id for p in proofs}:
        raise ValueError("Requested proof public ID is missing or hidden")
    for p in proofs:
        if proof_ids is not None and p.public_id not in proof_ids:
            continue
        responses: dict[str, bytes] = {}

        async def capture(path):
            if path not in responses:
                responses[path] = await get_body(application, path)
            return json.loads(responses[path])

        theorem = await capture(f"/theorems/{p.theorem_public_id}")
        tid = theorem["id"]
        await capture(f"/theorems/{tid}")
        premises = await capture(f"/theorems/{tid}/premises")
        theorem_proofs = await capture(f"/theorems/{tid}/proofs")
        await capture(f"/theorems/{tid}/used-in-theorems")
        proof = await capture(f"/proofs/{p.id}")
        steps = await capture(f"/proofs/{p.id}/steps")
        await capture(f"/proofs/{p.id}/state")
        proof_formulas = await capture(f"/proofs/{p.id}/formulas")
        await capture(f"/proofs/{p.id}/direct-dependencies")
        # The theorem's graph/comparison may use a different verified proof.
        verified = next((v for v in theorem_proofs if v["status"] == "verified"), None)
        verified_ids = {v for v in (p.id if proof["status"] == "verified" else None,
                                   verified["id"] if verified else None) if v is not None}
        if verified:
            await capture(f"/proofs/{verified['id']}/direct-dependencies")
        for pid in sorted(verified_ids):
            await capture(f"/proofs/{pid}/used-axioms")
        # Only the theorem panel's first verified proof has automatic system
        # checks. ProofDetail's selector requests validity only after a click.
        # The shared systems query may already be populated by ProofDetail,
        # even when external_checks is empty, so match that mounted UI too.
        if verified:
            for system in initial_comparison_systems(systems):
                await capture(f"/proofs/{verified['id']}/is-valid-in-system/{system['id']}")
        if proof["status"] == "draft" and steps:
            await capture(f"/proofs/{p.id}/steps/{steps[-1]['ord']}/followups")
        ids = {theorem["conclusion_formula_id"], *(v["formula"]["id"] for v in premises)}
        # The statement can mount either before or after proof formulas prime
        # React Query. Capture both possible initial batches, via the real API.
        for batch_ids in (ids, ids - {f["id"] for f in proof_formulas}):
            ordered = sorted(batch_ids)
            for start in range(0, len(ordered), BATCH_MAX_IDS):
                query = ",".join(map(str, ordered[start:start + BATCH_MAX_IDS]))
                await capture(f"/formulas/batch?ids={query}")
        files[f"proofs/{p.theorem_public_id}/{p.public_id}.json"] = response_map(responses)
        # Bound ORM/service caches for a whole-corpus build without changing
        # the immutable snapshot or any validation/serialization code.
        session.expunge_all()
        session.info.clear()
    return files


def write_data(output: Path, files: dict[str, bytes]) -> dict:
    digest = sha256()
    for name, body in sorted(files.items()):
        digest.update(name.encode() + b"\0" + str(len(body)).encode() + b"\0" + body)
    relative = "public-data/" + digest.hexdigest()
    raw_size = gzip_size = 0
    for name, body in sorted(files.items()):
        path = output / relative / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        compressed = io.BytesIO()
        with gzip.GzipFile(filename="", mode="wb", fileobj=compressed, mtime=0) as stream:
            stream.write(body)
        path.with_suffix(".json.gz").write_bytes(compressed.getvalue())
        raw_size += len(body)
        gzip_size += len(compressed.getvalue())
    return {"data_path": "/" + relative, "data_json_bytes": raw_size,
            "data_gzip_bytes": gzip_size, "data_proofs": len(files) - 1}
