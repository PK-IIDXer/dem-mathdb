"""Helpers for the content-database Alembic history."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def content_alembic_config(database_url: str | None = None) -> Config:
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "alembic"))
    if database_url is not None:
        config.set_main_option("sqlalchemy.url", database_url)
        config.attributes["database_url"] = database_url
    return config


@lru_cache(maxsize=1)
def content_schema_head() -> str:
    head = ScriptDirectory.from_config(content_alembic_config()).get_current_head()
    if head is None:
        raise RuntimeError("content Alembic history has no head revision")
    return head


def upgrade_content_schema(database_url: str, revision: str = "head") -> None:
    command.upgrade(content_alembic_config(database_url), revision)


def stamp_content_schema(database_url: str, revision: str) -> None:
    command.stamp(content_alembic_config(database_url), revision)
