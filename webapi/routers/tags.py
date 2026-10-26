from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select

from dem.api import DemServices
from dem.db.models.tag import Tag
from dem.services.system_tags import EXPLORATION_TAG
from webapi.deps import dem_services
from webapi.pagination import Cursor, Limit, read_page
from webapi.schemas import TagCreate, TagOut

router = APIRouter(tags=["tags"])


@router.get("/tags", response_model=list[TagOut])
def list_tags(
    response: Response,
    dem: DemServices = Depends(dem_services, scope="function"),
    limit: Limit = None,
    cursor: Cursor = None,
) -> list[TagOut]:
    if limit is None and cursor is None:
        return [
            tag for tag in dem.tags.list_all() if tag.name != EXPLORATION_TAG
        ]  # Legacy callers expect alphabetical order.
    return read_page(
        dem.session,
        Tag,
        select(Tag).where(Tag.name != EXPLORATION_TAG),
        response,
        limit,
        cursor,
    )


@router.post("/tags", response_model=TagOut, status_code=status.HTTP_201_CREATED)
def create_tag(body: TagCreate, dem: DemServices = Depends(dem_services, scope="function")) -> TagOut:
    return dem.tags.get_or_create(body.name)
