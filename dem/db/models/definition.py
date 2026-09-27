from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dem.db.base import Base
from dem.db.models.language import Formula, Symbol
from dem.db.ordering import tag_name_order
from dem.identity import new_public_id

if TYPE_CHECKING:
    from dem.db.models.tag import Tag


class Definition(Base):
    __tablename__ = "definition"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('predicate', 'function', 'logical', 'quant_prop', 'quant_term', "
            "'function_desc')",
            name="known_kind",
        ),
        CheckConstraint(
            "(kind = 'function_desc' AND existence_uniqueness_proof_id IS NOT NULL) "
            "OR (kind <> 'function_desc' AND existence_uniqueness_proof_id IS NULL)",
            name="function_desc_requires_proof",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, default=new_public_id
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    new_symbol_id: Mapped[int] = mapped_column(
        ForeignKey("symbol.id"), nullable=False, unique=True
    )
    requires_existence_proof: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false()
    )
    requires_uniqueness_proof: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false()
    )
    existence_uniqueness_proof_id: Mapped[int | None] = mapped_column(
        ForeignKey("proof.id")
    )
    display_formula_id: Mapped[int | None] = mapped_column(ForeignKey("formula.id"))
    description: Mapped[str | None] = mapped_column(Text)
    remarks: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    new_symbol: Mapped[Symbol] = relationship(lazy="joined")
    display_formula: Mapped["Formula | None"] = relationship(lazy="joined")
    tags: Mapped[list["Tag"]] = relationship(
        "Tag",
        secondary="definition_tag",
        lazy="selectin",
        viewonly=True,
        order_by=tag_name_order,
    )
    formal_params: Mapped[list[DefinitionFormalParam]] = relationship(
        back_populates="definition",
        cascade="all, delete-orphan",
        order_by="DefinitionFormalParam.ord",
        lazy="raise",
    )


class DefinitionFormalParam(Base):
    __tablename__ = "definition_formal_param"
    __table_args__ = (
        CheckConstraint("ord >= 0", name="ord_nonnegative"),
    )

    definition_id: Mapped[int] = mapped_column(
        ForeignKey("definition.id", ondelete="CASCADE"), primary_key=True
    )
    ord: Mapped[int] = mapped_column(Integer, primary_key=True)
    param_symbol_id: Mapped[int] = mapped_column(ForeignKey("symbol.id"), nullable=False)

    definition: Mapped[Definition] = relationship(back_populates="formal_params")
    param_symbol: Mapped[Symbol] = relationship(lazy="joined")
