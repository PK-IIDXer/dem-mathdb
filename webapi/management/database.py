from __future__ import annotations

from pathlib import Path
from uuid import UUID

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session

from webapi.management.models import Account


def create_management_engine(database_url: str) -> Engine:
    """Create an engine for the management DB, including SQLite FK enforcement."""
    connect_args = (
        {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    )
    engine = create_engine(database_url, connect_args=connect_args)
    if database_url.startswith("sqlite"):
        event.listen(
            engine,
            "connect",
            lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"),
        )
    return engine


def upgrade_management_schema(database_url: str) -> None:
    """Create or upgrade the management schema exclusively through Alembic."""
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).with_name("migrations"))
    )
    config.attributes["database_url"] = database_url
    command.upgrade(config, "head")


def ensure_development_account(
    session: Session,
    *,
    account_id: UUID,
    external_subject: str,
    display_name: str,
) -> Account:
    """Idempotently create the single development account used in Phase 3."""
    account = session.get(Account, account_id)
    if account is None:
        account = Account(
            id=account_id,
            external_subject=external_subject,
            email=None,
            display_name=display_name,
        )
        session.add(account)
        session.flush()
    return account
