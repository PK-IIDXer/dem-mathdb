"""Opt-in ID cursor pagination; legacy list responses remain arrays."""

from __future__ import annotations

import base64
import binascii
from typing import Annotated, TypeVar

from fastapi import HTTPException, Query, Response
from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from dem.db.models.definition import Definition
from dem.db.models.inference import Axiom
from dem.db.models.language import Formula
from dem.db.models.tag import Tag
from dem.db.models.theorem import Theorem

Limit = Annotated[int | None, Query(ge=1, le=500)]
Cursor = Annotated[str | None, Query(max_length=28)]
NEXT_CURSOR_HEADER = "X-Next-Cursor"
T = TypeVar("T", Formula, Axiom, Definition, Theorem, Tag)
Named = TypeVar("Named", Axiom, Definition, Theorem)


def encode_cursor(id: int) -> str:
    return base64.b64encode(str(id).encode("ascii")).decode("ascii")


def decode_cursor(cursor: str) -> int:
    try:
        decoded = base64.b64decode(cursor, validate=True).decode("ascii")
        if not decoded.isdecimal() or len(decoded) > 19:
            raise ValueError
        id = int(decoded)
        if not 0 < id <= 2**63 - 1 or encode_cursor(id) != cursor:
            raise ValueError
        return id
    except (ValueError, UnicodeError, binascii.Error):
        raise HTTPException(status_code=422, detail="Invalid pagination cursor") from None


def named_query(
    model: type[Named],
    search: str | None,
    tag_ids: list[int] | None,
    exclude_tag_ids: list[int] | None = None,
) -> Select[tuple[Named]]:
    """Match service search semantics, filtering in SQL before the page limit."""
    stmt = select(model)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(model.name.ilike(like), model.description.ilike(like)))
    if tag_ids:
        # ANY matching tag, without multiplying rows when several tags match.
        stmt = stmt.where(model.tags.any(Tag.id.in_(tag_ids)))
    if exclude_tag_ids:
        # Independent of the inclusive ANY filter above: carrying any excluded
        # tag removes a row even when another tag satisfies tag_id.
        stmt = stmt.where(~model.tags.any(Tag.id.in_(exclude_tag_ids)))
    return stmt


def read_page(
    session: Session,
    model: type[T],
    stmt: Select[tuple[T]],
    response: Response,
    limit: int | None,
    cursor: str | None,
) -> list[T]:
    if cursor is not None:
        stmt = stmt.where(model.id > decode_cursor(cursor))
        # Following a cursor without a limit is still a bounded page.
        if limit is None:
            limit = 50
    stmt = stmt.order_by(model.id)
    if limit is not None:
        stmt = stmt.limit(limit + 1)
    rows = list(session.scalars(stmt))
    if limit is not None and len(rows) > limit:
        rows = rows[:limit]
        response.headers[NEXT_CURSOR_HEADER] = encode_cursor(rows[-1].id)
    return rows
