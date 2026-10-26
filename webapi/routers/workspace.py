from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends
from starlette.background import BackgroundTask
from starlette.responses import FileResponse

from webapi.deps import WorkspaceRequestContext, get_workspace_request_context
from webapi.schemas import WorkspaceInfoOut
from webapi.workspace_export import WorkspaceExportMetadata, create_workspace_export


router = APIRouter(tags=["workspace"])


def _safe_filename(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip(".-")
    return normalized or "workspace"


@router.get("/workspace/info", response_model=WorkspaceInfoOut)
def workspace_info(
    context: WorkspaceRequestContext = Depends(get_workspace_request_context),
) -> WorkspaceInfoOut:
    return WorkspaceInfoOut(
        title=context.title,
        local_namespace_name=context.local_namespace_name,
    )


@router.get("/workspace/export", response_class=FileResponse)
def export_workspace(
    context: WorkspaceRequestContext = Depends(get_workspace_request_context),
) -> FileResponse:
    """Download an owned workspace as a machine-readable package archive."""
    with context.api.session() as dem:
        result = create_workspace_export(
            dem.session,
            WorkspaceExportMetadata(
                package=f"workspace.{context.slug}",
                description=f"Workspace export: {context.title or 'Local workspace'}",
            ),
        )
    filename = f"{_safe_filename(context.slug)}-{context.workspace_id}.dempkg"
    return FileResponse(
        path=result.path,
        media_type="application/vnd.dem.workspace+zip",
        filename=filename,
        background=BackgroundTask(Path(result.path).unlink, missing_ok=True),
    )
