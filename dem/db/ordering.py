"""Dialect-independent ordering helpers for UTF-8 text."""

from __future__ import annotations

from sqlalchemy import LargeBinary, cast, literal_column
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql import ColumnElement
from sqlalchemy.sql.functions import FunctionElement


class _Utf8SortKey(FunctionElement[bytes]):
    type = LargeBinary()
    inherit_cache = True


@compiles(_Utf8SortKey)
def _compile_utf8_sort_key(
    element: _Utf8SortKey, compiler, **kwargs: object
) -> str:
    expression = next(iter(element.clauses))
    return compiler.process(cast(expression, LargeBinary), **kwargs)


@compiles(_Utf8SortKey, "postgresql")
def _compile_postgresql_utf8_sort_key(
    element: _Utf8SortKey, compiler, **kwargs: object
) -> str:
    expression = compiler.process(next(iter(element.clauses)), **kwargs)
    return f"convert_to({expression}, 'UTF8')"


def utf8_sort_key(expression: ColumnElement[str]) -> ColumnElement[bytes]:
    """Return UTF-8 bytes without PostgreSQL's text-to-bytea escape parsing."""
    return _Utf8SortKey(expression)


def compile_utf8_sort_key(expression: str, dialect: Dialect) -> str:
    """Compile the shared expression for a trusted SQL identifier fragment."""
    return str(utf8_sort_key(literal_column(expression)).compile(dialect=dialect))


def tag_name_order() -> tuple[ColumnElement[bytes], ColumnElement[int]]:
    """Resolve Tag lazily so model imports remain acyclic."""
    from dem.db.models.tag import Tag

    return utf8_sort_key(Tag.name), Tag.id
