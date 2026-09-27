from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select

from dem.api import DemServices
from dem.db.models.tag import Tag
from webapi.deps import dem_services
from webapi.pagination import Cursor, Limit, read_page
from webapi.schemas import TagCreate, TagOut

router = APIRouter(tags=["tags"])


@router.get("/tags", response_model=list[TagOut])
def list_tags(
    response: Response,
    dem: DemServices = Depends(dem_services),
    limit: Limit = None,
    cursor: Cursor = None,
) -> list[TagOut]:
    if limit is None and cursor is None:
        return dem.tags.list_all()  # Legacy callers expect alphabetical order.
    return read_page(dem.session, Tag, select(Tag), response, limit, cursor)


@router.post("/tags", response_model=TagOut, status_code=status.HTTP_201_CREATED)
def create_tag(body: TagCreate, dem: DemServices = Depends(dem_services)) -> TagOut:
    return dem.tags.get_or_create(body.name)
