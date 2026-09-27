from __future__ import annotations

import hashlib
import shutil
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import sqlalchemy
from sqlalchemy.orm import Session

from webapi.management.models import Workspace
from webapi.management.schema_revision import content_schema_head


SNAPSHOT_CACHE_VERSION = "2"
DEFAULT_WORKSPACE_TEMPLATE_PATH = Path("build/template.db")


def production_fingerprint(repository: Path | None = None) -> str:
    """Mirror the test snapshot fingerprint without importing test code."""
    repository = repository or Path(__file__).resolve().parents[2]
    digest = hashlib.sha256()
    digest.update(SNAPSHOT_CACHE_VERSION.encode())
    digest.update(sys.version.encode())
    digest.update(sqlalchemy.__version__.encode())
    paths = [
        *sorted((repository / "dem").rglob("*.py")),
        *sorted((repository / "demlang").rglob("*.py")),
        repository / "pyproject.toml",
    ]
    for path in paths:
        digest.update(path.relative_to(repository).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:20]


def template_fingerprint_path(template_path: Path) -> Path:
    return template_path.with_name(f"{template_path.name}.fingerprint")


def write_template_fingerprint(
    template_path: Path, repository: Path | None = None
) -> str:
    fingerprint = production_fingerprint(repository)
    template_fingerprint_path(template_path).write_text(
        f"{fingerprint}\n", encoding="ascii"
    )
    return fingerprint


def validate_workspace_template(
    template_path: Path, repository: Path | None = None
) -> str:
    """Fail fast when the template is absent, stale, or not a valid SQLite DB."""
    if not template_path.is_file():
        raise RuntimeError(
            f"workspace template does not exist: {template_path}; "
            "run scripts/build_workspace_template.py"
        )

    fingerprint_path = template_fingerprint_path(template_path)
    if not fingerprint_path.is_file():
        raise RuntimeError(
            f"workspace template fingerprint does not exist: {fingerprint_path}; "
            "rebuild the workspace template"
        )
    actual = fingerprint_path.read_text(encoding="ascii").strip()
    expected = production_fingerprint(repository)
    if actual != expected:
        raise RuntimeError(
            "workspace template fingerprint does not match production code; "
            "rebuild the workspace template"
        )

    try:
        with closing(sqlite3.connect(template_path)) as connection:
            if connection.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise RuntimeError("workspace template failed SQLite quick_check")
            revision = embedded_schema_revision(connection)
            expected_revision = content_schema_head()
            if revision is None:
                raise RuntimeError(
                    "workspace template has no embedded Alembic revision; "
                    "rebuild the workspace template"
                )
            if revision != expected_revision:
                raise RuntimeError(
                    "workspace template schema revision does not match Alembic head; "
                    "rebuild the workspace template"
                )
    except sqlite3.DatabaseError as exc:
        raise RuntimeError("workspace template is not a valid SQLite database") from exc
    return actual


def embedded_schema_revision(connection: sqlite3.Connection) -> str | None:
    version_table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'alembic_version'"
    ).fetchone()
    if version_table is None:
        return None
    row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    return None if row is None else str(row[0])


def create_workspace_from_template(
    session: Session,
    *,
    account_id: UUID,
    slug: str,
    title: str,
    template_path: Path,
    workspace_path: Path,
    visibility: str = "public",
    workspace_id: UUID | None = None,
) -> Workspace:
    """Provision one workspace by copying a verified build-time template."""
    fingerprint = validate_workspace_template(template_path)
    schema_revision = content_schema_head()
    workspace_path.parent.mkdir(parents=True, exist_ok=True)
    if workspace_path.exists():
        raise FileExistsError(f"workspace database already exists: {workspace_path}")

    try:
        with template_path.open("rb") as source, workspace_path.open("xb") as target:
            shutil.copyfileobj(source, target)
        workspace = Workspace(
            id=workspace_id or uuid4(),
            account_id=account_id,
            slug=slug,
            title=title,
            visibility=visibility,
            storage_uri=f"sqlite+pysqlite:///{workspace_path.resolve().as_posix()}",
            template_fingerprint=fingerprint,
            schema_revision=schema_revision,
            schema_state="ready",
            schema_error=None,
            schema_checked_at=datetime.now(UTC),
        )
        session.add(workspace)
        session.flush()
    except BaseException:
        workspace_path.unlink(missing_ok=True)
        raise
    return workspace
