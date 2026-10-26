"""Distribution metadata; never evidence for mathematical validation."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, JSON, Text, UniqueConstraint, false, func
from sqlalchemy.orm import Mapped, mapped_column

from dem.db.base import Base


class Package(Base):
    __tablename__ = "package"
    __table_args__ = (CheckConstraint("visibility IN ('public', 'private')", name="known_visibility"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    owner: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(Text, nullable=False, server_default="private")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PackageRelease(Base):
    __tablename__ = "package_release"
    __table_args__ = (UniqueConstraint("package_id", "version"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("package.id"), nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    dem_runtime_range: Mapped[str] = mapped_column(Text, nullable=False)
    manifest: Mapped[dict] = mapped_column(JSON, nullable=False)
    content_digest: Mapped[str | None] = mapped_column(Text)
    yanked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReleaseDependency(Base):
    __tablename__ = "release_dependency"
    release_id: Mapped[int] = mapped_column(ForeignKey("package_release.id"), primary_key=True)
    depends_package_id: Mapped[int] = mapped_column(ForeignKey("package.id"), primary_key=True)
    range: Mapped[str] = mapped_column(Text, nullable=False)


class ReleaseLockEntry(Base):
    __tablename__ = "release_lock_entry"
    __table_args__ = (CheckConstraint("release_id <> locked_release_id", name="not_self"),)
    release_id: Mapped[int] = mapped_column(ForeignKey("package_release.id"), primary_key=True)
    locked_release_id: Mapped[int] = mapped_column(ForeignKey("package_release.id"), primary_key=True)


class InstalledRelease(Base):
    __tablename__ = "installed_release"
    # Content databases are already isolated per workspace.
    release_id: Mapped[int] = mapped_column(ForeignKey("package_release.id"), primary_key=True)
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
