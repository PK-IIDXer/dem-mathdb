from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Index,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dem.db.base import Base
from dem.identity import new_public_id


class Namespace(Base):
    __tablename__ = "namespace"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("namespace.id"))

    parent: Mapped[Namespace | None] = relationship(remote_side=[id], lazy="joined")


class FormulaType(Base):
    __tablename__ = "formula_type"
    __table_args__ = (
        CheckConstraint(
            "code IN ('term', 'proposition')", name="known_code"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    remarks: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SymbolType(Base):
    __tablename__ = "symbol_type"
    __table_args__ = (
        CheckConstraint(
            "fixed_arity IS NULL OR fixed_arity >= 0",
            name="fixed_arity_nonnegative",
        ),
        CheckConstraint(
            "(input_formula_type_id IS NULL AND fixed_arity = 0) "
            "OR (input_formula_type_id IS NOT NULL)",
            name="input_or_zero_arity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    output_formula_type_id: Mapped[int] = mapped_column(
        ForeignKey("formula_type.id"), nullable=False
    )
    input_formula_type_id: Mapped[int | None] = mapped_column(ForeignKey("formula_type.id"))
    fixed_arity: Mapped[int | None] = mapped_column(Integer)
    is_quantifier: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false()
    )
    remarks: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    output_formula_type: Mapped[FormulaType] = relationship(
        foreign_keys=[output_formula_type_id], lazy="joined"
    )
    input_formula_type: Mapped[FormulaType | None] = relationship(
        foreign_keys=[input_formula_type_id], lazy="joined"
    )


class Symbol(Base):
    __tablename__ = "symbol"
    __table_args__ = (
        CheckConstraint("arity >= 0", name="arity_nonnegative"),
        CheckConstraint("notation_kind IN ('prefix', 'infix')", name="known_notation_kind"),
        CheckConstraint(
            "(notation_kind = 'infix' AND precedence IS NOT NULL) "
            "OR (notation_kind = 'prefix' AND precedence IS NULL)",
            name="precedence_matches_notation_kind",
        ),
        CheckConstraint(
            "notation_kind = 'prefix' OR arity = 2",
            name="infix_requires_arity_two",
        ),
        UniqueConstraint("namespace_id", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, default=new_public_id
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    symbol_type_id: Mapped[int] = mapped_column(ForeignKey("symbol_type.id"), nullable=False)
    arity: Mapped[int] = mapped_column(Integer, nullable=False)
    is_primitive: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false()
    )
    namespace_id: Mapped[int] = mapped_column(ForeignKey("namespace.id"), nullable=False)
    notation_kind: Mapped[str] = mapped_column(Text, nullable=False, server_default="prefix")
    precedence: Mapped[int | None] = mapped_column(Integer)
    latex_template: Mapped[str | None] = mapped_column(Text)
    remarks: Mapped[str | None] = mapped_column(Text)
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    symbol_type: Mapped[SymbolType] = relationship(lazy="joined")
    namespace: Mapped[Namespace] = relationship(lazy="joined")
    aliases: Mapped[list[SymbolAlias]] = relationship(
        back_populates="symbol", cascade="all, delete-orphan", lazy="raise"
    )


class SymbolAlias(Base):
    __tablename__ = "symbol_alias"
    __table_args__ = (
        CheckConstraint("source IN ('builtin', 'user')", name="known_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol_id: Mapped[int] = mapped_column(
        ForeignKey("symbol.id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)

    symbol: Mapped[Symbol] = relationship(back_populates="aliases")


class SymbolRole(Base):
    __tablename__ = "symbol_role"
    __table_args__ = (
        CheckConstraint(
            "role IN ('implication', 'universal_quantifier', 'biconditional', 'equality')",
            name="known_role",
        ),
    )

    role: Mapped[str] = mapped_column(Text, primary_key=True)
    symbol_id: Mapped[int] = mapped_column(ForeignKey("symbol.id"), nullable=False, unique=True)
    remarks: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    symbol: Mapped[Symbol] = relationship(lazy="joined")


class Formula(Base):
    __tablename__ = "formula"
    __table_args__ = (
        CheckConstraint("token_count > 0", name="token_count_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, default=new_public_id
    )
    formula_type_id: Mapped[int] = mapped_column(
        ForeignKey("formula_type.id"), nullable=False
    )
    hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    remarks: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    formula_type: Mapped[FormulaType] = relationship(lazy="joined")
    tokens: Mapped[list[FormulaToken]] = relationship(
        back_populates="formula",
        cascade="all, delete-orphan",
        order_by="FormulaToken.position",
        lazy="raise",
    )


class FormulaToken(Base):
    __tablename__ = "formula_token"
    __table_args__ = (
        UniqueConstraint("formula_id", "position"),
        Index("ix_formula_token_symbol_formula", "symbol_id", "formula_id"),
        CheckConstraint("position >= 0", name="position_nonnegative"),
        CheckConstraint(
            "(symbol_id IS NOT NULL AND de_bruijn_index IS NULL) "
            "OR (symbol_id IS NULL AND de_bruijn_index IS NOT NULL AND de_bruijn_index >= 0)",
            name="exactly_one_kind",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    formula_id: Mapped[int] = mapped_column(
        ForeignKey("formula.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol_id: Mapped[int | None] = mapped_column(ForeignKey("symbol.id"))
    de_bruijn_index: Mapped[int | None] = mapped_column(Integer)

    formula: Mapped[Formula] = relationship(back_populates="tokens")
    symbol: Mapped[Symbol | None] = relationship(lazy="joined")
