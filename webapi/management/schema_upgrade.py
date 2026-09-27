"""Offline state machine for safely upgrading SQLite workspace files."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import select
from sqlalchemy.orm import Session

from webapi.management.database import (
    create_management_engine,
    upgrade_management_schema,
)
from webapi.management.deployment_lock import DeploymentLock, deployment_lock_path
from webapi.management.models import Workspace
from webapi.management.schema_revision import (
    content_alembic_config,
    content_schema_head,
    stamp_content_schema,
)
from webapi.management.schema_state import (
    SchemaFailure,
    blocked_update,
    ready_update,
    upgrading_update,
)
from webapi.management.sqlite_workspace import (
    EXPECTED_SQLITE_TRIGGERS,
    LEGACY_SCHEMA_REVISION,
    LEGACY_SCHEMA_SIGNATURE,
    basic_read_smoke,
    inspect_sqlite_workspace,
    pending_backup_path,
    publish_shadow,
    sqlite_backup,
    sqlite_path_from_url,
    workspace_backup_path,
    workspace_shadow_path,
)
from webapi.management.workspace import production_fingerprint


FaultInjector = Callable[[str, UUID], None]


@dataclass(frozen=True)
class WorkspaceUpgradeResult:
    workspace_id: UUID
    outcome: str
    from_revision: str | None
    to_revision: str | None
    detail: str


def _no_fault(point: str, workspace_id: UUID) -> None:
    del point, workspace_id


def _apply_update(workspace: Workspace, update) -> None:
    workspace.schema_state = update.state
    workspace.schema_revision = update.revision
    workspace.schema_error = update.error
    workspace.schema_checked_at = update.checked_at


def _block(
    session: Session,
    workspace: Workspace,
    revision: str | None,
    failure: SchemaFailure,
) -> WorkspaceUpgradeResult:
    _apply_update(workspace, blocked_update(revision, failure))
    session.commit()
    return WorkspaceUpgradeResult(
        workspace.id, "upgrade_blocked", revision, None, failure.encode()
    )


def _migration_revisions(current: str, head: str) -> list[str]:
    script = ScriptDirectory.from_config(content_alembic_config())
    return [
        revision.revision
        for revision in reversed(list(script.iterate_revisions(head, current)))
    ]


def _failure_from_exception(exc: BaseException) -> SchemaFailure:
    message = str(exc)
    formula_match = re.search(r"formula\s+(\d+)\s+is not well-formed", message)
    if formula_match:
        return SchemaFailure(
            "formula_not_well_formed",
            message,
            int(formula_match.group(1)),
        )
    return SchemaFailure("schema_upgrade_failed", message)


def _postflight(path: Path, head: str) -> SchemaFailure | None:
    inspection = inspect_sqlite_workspace(path)
    if inspection.quick_check != "ok":
        return SchemaFailure("quick_check_failed", inspection.quick_check)
    if inspection.revision != head:
        return SchemaFailure(
            "wrong_schema_revision",
            f"expected {head}, found {inspection.revision}",
        )
    if inspection.incomplete_formulas:
        formula_id = inspection.incomplete_formulas[0][0]
        return SchemaFailure(
            "incomplete_formula",
            f"formula {formula_id} has an incomplete token sequence",
            formula_id,
        )
    if inspection.triggers != EXPECTED_SQLITE_TRIGGERS:
        missing = sorted(EXPECTED_SQLITE_TRIGGERS - inspection.triggers)
        unexpected = sorted(inspection.triggers - EXPECTED_SQLITE_TRIGGERS)
        return SchemaFailure(
            "trigger_set_mismatch",
            f"missing={missing}; unexpected={unexpected}",
        )
    try:
        basic_read_smoke(path)
    except Exception as exc:
        return SchemaFailure("read_smoke_failed", str(exc))
    return None


def upgrade_one_workspace(
    session: Session,
    workspace: Workspace,
    *,
    dry_run: bool,
    fault_injector: FaultInjector = _no_fault,
) -> WorkspaceUpgradeResult:
    """Inspect and, unless dry-run, atomically upgrade one workspace."""
    head = content_schema_head()
    try:
        workspace_path = sqlite_path_from_url(workspace.storage_uri)
        inspection = inspect_sqlite_workspace(workspace_path)
    except Exception as exc:
        return _block(
            session,
            workspace,
            workspace.schema_revision,
            SchemaFailure("workspace_inspection_failed", str(exc)),
        )

    current = inspection.revision
    if inspection.quick_check != "ok":
        return _block(
            session,
            workspace,
            current,
            SchemaFailure("quick_check_failed", inspection.quick_check),
        )
    if inspection.incomplete_formulas:
        formula_id = inspection.incomplete_formulas[0][0]
        return _block(
            session,
            workspace,
            current,
            SchemaFailure(
                "incomplete_formula",
                f"formula {formula_id} has an incomplete token sequence",
                formula_id,
            ),
        )
    if current is None:
        if inspection.schema_signature != LEGACY_SCHEMA_SIGNATURE:
            return _block(
                session,
                workspace,
                None,
                SchemaFailure(
                    "unknown_legacy_schema",
                    f"unknown schema signature {inspection.schema_signature}",
                ),
            )
        current = LEGACY_SCHEMA_REVISION

    if current == head:
        postflight_failure = _postflight(workspace_path, head)
        if postflight_failure is not None:
            return _block(session, workspace, current, postflight_failure)
        _apply_update(workspace, ready_update(head))
        if workspace.template_fingerprint is None:
            workspace.template_fingerprint = production_fingerprint()
        session.commit()
        pending = pending_backup_path(workspace_path, workspace.id)
        retained = workspace_backup_path(workspace_path, workspace.id)
        if pending.exists():
            retained.parent.mkdir(parents=True, exist_ok=True)
            pending.replace(retained)
        workspace_shadow_path(workspace_path, workspace.id).unlink(missing_ok=True)
        return WorkspaceUpgradeResult(
            workspace.id, "ready", inspection.revision, head, "already at head"
        )

    revisions = _migration_revisions(current, head)
    if dry_run:
        return WorkspaceUpgradeResult(
            workspace.id,
            "would_upgrade",
            inspection.revision,
            head,
            "legacy="
            f"{current if inspection.revision is None else None}; "
            f"migrations={revisions}",
        )

    _apply_update(workspace, upgrading_update(inspection.revision))
    session.commit()
    shadow = workspace_shadow_path(workspace_path, workspace.id)
    pending_backup = pending_backup_path(workspace_path, workspace.id)
    published = False
    try:
        if shadow.exists():
            inspect_sqlite_workspace(shadow)
            shadow.unlink()
        sqlite_backup(workspace_path, pending_backup)
        fault_injector("after_backup", workspace.id)
        sqlite_backup(workspace_path, shadow)
        shadow_url = f"sqlite+pysqlite:///{shadow.as_posix()}"
        if inspection.revision is None:
            stamp_content_schema(shadow_url, LEGACY_SCHEMA_REVISION)
            fault_injector("after_stamp", workspace.id)
        config = content_alembic_config(shadow_url)
        for revision in revisions:
            command.upgrade(config, revision)
            fault_injector(f"after_migration:{revision}", workspace.id)
        failure = _postflight(shadow, head)
        if failure is not None:
            raise WorkspaceSchemaBlocked(failure)
        fault_injector("after_postflight", workspace.id)
        fault_injector("before_publish", workspace.id)
        publish_shadow(shadow, workspace_path)
        published = True
        fault_injector("after_publish", workspace.id)
    except WorkspaceSchemaBlocked as exc:
        shadow.unlink(missing_ok=True)
        return _block(session, workspace, inspection.revision, exc.failure)
    except Exception as exc:
        if published:
            # This models a process crash at the only non-transactional boundary.
            # The next run trusts the embedded head and converges the management row.
            raise
        shadow.unlink(missing_ok=True)
        return _block(
            session,
            workspace,
            inspection.revision,
            _failure_from_exception(exc),
        )

    retained_backup = workspace_backup_path(workspace_path, workspace.id)
    retained_backup.parent.mkdir(parents=True, exist_ok=True)
    pending_backup.replace(retained_backup)
    workspace.template_fingerprint = production_fingerprint()
    _apply_update(workspace, ready_update(head))
    session.commit()
    return WorkspaceUpgradeResult(
        workspace.id, "upgraded", inspection.revision, head, str(retained_backup)
    )


class WorkspaceSchemaBlocked(RuntimeError):
    def __init__(self, failure: SchemaFailure) -> None:
        super().__init__(failure.message)
        self.failure = failure


def upgrade_all_workspaces(
    management_database_url: str,
    *,
    dry_run: bool = False,
    workspace_ids: set[UUID] | None = None,
    fault_injector: FaultInjector = _no_fault,
) -> list[WorkspaceUpgradeResult]:
    """Acquire the exclusive deployment lock and process every selected row."""
    lock_path = deployment_lock_path(management_database_url)
    with DeploymentLock(lock_path, exclusive=True):
        upgrade_management_schema(management_database_url)
        engine = create_management_engine(management_database_url)
        try:
            with Session(engine) as session:
                query = select(Workspace).order_by(Workspace.created_at, Workspace.id)
                if workspace_ids:
                    query = query.where(Workspace.id.in_(workspace_ids))
                workspaces = list(session.scalars(query))
                return [
                    upgrade_one_workspace(
                        session,
                        workspace,
                        dry_run=dry_run,
                        fault_injector=fault_injector,
                    )
                    for workspace in workspaces
                ]
        finally:
            engine.dispose()
