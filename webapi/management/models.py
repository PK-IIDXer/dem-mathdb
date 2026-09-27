from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class ManagementBase(DeclarativeBase):
    """Metadata used only by the management-database Alembic history."""


class Account(ManagementBase):
    __tablename__ = "account"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    external_subject: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Workspace(ManagementBase):
    __tablename__ = "workspace"
    __table_args__ = (
        CheckConstraint(
            "visibility IN ('public', 'private')", name="known_visibility"
        ),
        CheckConstraint(
            "schema_state IN ('ready', 'upgrading', 'upgrade_blocked')",
            name="known_schema_state",
        ),
        UniqueConstraint("account_id", "slug"),
        UniqueConstraint("storage_uri"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("account.id"), nullable=False
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="public"
    )
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    template_fingerprint: Mapped[str | None] = mapped_column(Text)
    schema_revision: Mapped[str | None] = mapped_column(Text)
    schema_state: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="upgrading"
    )
    schema_error: Mapped[str | None] = mapped_column(Text)
    schema_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WorkspaceMember(ManagementBase):
    __tablename__ = "workspace_member"

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspace.id"), primary_key=True
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("account.id"), primary_key=True
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
