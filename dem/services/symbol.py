from __future__ import annotations

import re

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from dem.db.models.language import FormulaToken, FormulaType, Namespace, Symbol, SymbolAlias, SymbolRole, SymbolType
from dem.db.ordering import utf8_sort_key
from dem.errors import ConflictError, NotFoundError, ValidationError
from dem.identity import DEFAULT_NAMESPACE_NAME, ensure_namespace, new_entity_public_id
from dem.services.formula import flush_pending_symbol_usage_counts
from dem.types import SymbolTypeName
from dem.symbol_aliases import BUILTIN_ALIASES


VALID_ROLES = frozenset(
    {"implication", "universal_quantifier", "biconditional", "equality"}
)

ROLE_REQUIREMENTS = {
    "implication": (SymbolTypeName.LOGICAL, 2),
    "universal_quantifier": (SymbolTypeName.QUANT_PROP, 1),
    "biconditional": (SymbolTypeName.LOGICAL, 2),
    "equality": (SymbolTypeName.PREDICATE, 2),
}

VALID_NOTATION_KINDS = frozenset({"prefix", "infix"})


_SLOT = re.compile(r"#\d+")


def shape_signature(name: str, symbol_type: SymbolType, arity: int,
                    notation_kind: str, latex_template: str | None) -> tuple:
    """Necessary symbol-level injectivity check, not a formula round-trip test."""
    template = (latex_template or name).strip()
    if _SLOT.search(template):
        return ("slots", _SLOT.sub("□", template))
    if symbol_type.is_quantifier:
        return ("binder", template)
    if arity == 0:
        return ("atom", template)
    if notation_kind == "infix":
        return ("infix", template)
    return ("apply", template, arity)


def symbol_shape(symbol: Symbol) -> tuple:
    return shape_signature(symbol.name, symbol.symbol_type, symbol.arity,
                           symbol.notation_kind, symbol.latex_template)


class SymbolService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_formula_type(self, id: int) -> FormulaType:
        row = self._session.get(FormulaType, id)
        if row is None:
            raise NotFoundError("FormulaType", id)
        return row

    def get_formula_type_by_name(self, name: str) -> FormulaType:
        row = self._session.scalar(select(FormulaType).where(FormulaType.name == name))
        if row is None:
            raise NotFoundError("FormulaType", name)
        return row

    def list_formula_types(self) -> list[FormulaType]:
        return list(self._session.scalars(select(FormulaType).order_by(FormulaType.id)))

    def get_symbol_type(self, id: int) -> SymbolType:
        row = self._session.get(SymbolType, id)
        if row is None:
            raise NotFoundError("SymbolType", id)
        return row

    def get_symbol_type_by_name(self, name: str) -> SymbolType:
        row = self._session.scalar(select(SymbolType).where(SymbolType.name == name))
        if row is None:
            raise NotFoundError("SymbolType", name)
        return row

    def list_symbol_types(self) -> list[SymbolType]:
        return list(self._session.scalars(select(SymbolType).order_by(SymbolType.id)))

    def register(
        self,
        name: str,
        symbol_type_id: int,
        arity: int,
        is_primitive: bool = False,
        notation_kind: str = "prefix",
        precedence: int | None = None,
        latex_template: str | None = None,
        remarks: str | None = None,
        namespace: str = DEFAULT_NAMESPACE_NAME,
        namespace_id: int | None = None,
        public_id_key: str | None = None,
    ) -> Symbol:
        """Register a symbol.

        ``public_id_key`` is the seed / package-import path for keeping a
        symbol's birth identity (``dem.identity.public_id_from_key``); the REST
        API never passes it.
        """
        namespace_row = (
            self._session.get(Namespace, namespace_id)
            if namespace_id is not None
            else ensure_namespace(self._session, namespace)
        )
        if namespace_row is None:
            raise NotFoundError("Namespace", namespace_id or namespace)
        public_id = new_entity_public_id("symbol", namespace_row.name, name, public_id_key)
        symbol_type = self.get_symbol_type(symbol_type_id)
        if arity < 0:
            raise ValidationError("arity must be >= 0")
        if symbol_type.fixed_arity is not None and arity != symbol_type.fixed_arity:
            raise ValidationError(
                f"arity must be {symbol_type.fixed_arity} for SymbolType {symbol_type.name!r}"
            )
        self._validate_notation(notation_kind, precedence, arity)
        existing = self._session.scalar(
            select(Symbol).where(
                Symbol.namespace_id == namespace_row.id, Symbol.name == name
            )
        )
        if existing is not None:
            raise ConflictError("Symbol", "name", name)
        alias = self._session.scalar(select(SymbolAlias).where(SymbolAlias.alias == name))
        if alias is not None:
            raise ConflictError("Symbol", "name", name, code="symbol.alias_collision")
        if public_id_key is not None and self._session.scalar(
            select(Symbol.id).where(Symbol.public_id == public_id)
        ) is not None:
            raise ConflictError("Symbol", "public_id", public_id)

        latex_template = self._normalize_latex_template(latex_template)
        self._validate_display_uniqueness(
            name, symbol_type, arity, notation_kind, latex_template,
            namespace_id=namespace_row.id,
        )
        symbol = Symbol(
            public_id=public_id,
            name=name,
            namespace_id=namespace_row.id,
            symbol_type_id=symbol_type_id,
            arity=arity,
            is_primitive=is_primitive,
            notation_kind=notation_kind,
            precedence=precedence,
            latex_template=self._normalize_latex_template(latex_template),
            remarks=remarks,
        )
        self._session.add(symbol)
        self._session.flush()
        # Symbols introduced by later seed layers receive their built-in
        # spellings immediately as well; partial cascade snapshots should have
        # the same parser vocabulary as a completed seed_all() database.
        for alias_name, target_name in BUILTIN_ALIASES.items():
            if target_name == name:
                self.add_alias(symbol.id, alias_name, source="builtin")
        return symbol

    def get(self, id: int) -> Symbol:
        row = self._session.get(Symbol, id)
        if row is None:
            raise NotFoundError("Symbol", id)
        return row

    def get_by_name(self, name: str, namespace: str | None = None) -> Symbol:
        stmt = select(Symbol).where(Symbol.name == name)
        if namespace is not None:
            stmt = stmt.join(Namespace).where(Namespace.name == namespace)
        rows = list(self._session.scalars(stmt.limit(2)))
        if not rows:
            raise NotFoundError("Symbol", name)
        if len(rows) > 1:
            raise ValidationError(
                f"symbol name {name!r} is ambiguous",
                code="symbol.ambiguous_name",
                details={"name": name},
            )
        return rows[0]

    def list_with_usage(
        self, symbol_type_id: int | None = None
    ) -> list[tuple[Symbol, int]]:
        """Return symbols with distinct-formula usage counts for completion UIs."""
        if symbol_type_id is not None:
            self.get_symbol_type(symbol_type_id)
        flush_pending_symbol_usage_counts(self._session)
        stmt = select(Symbol, Symbol.usage_count).order_by(Symbol.id)
        if symbol_type_id is not None:
            stmt = stmt.where(Symbol.symbol_type_id == symbol_type_id)
        return [(symbol, count) for symbol, count in self._session.execute(stmt)]

    def recalculate_usage_counts(self) -> None:
        """Rebuild persisted distinct-formula counts for an existing database."""
        flush_pending_symbol_usage_counts(self._session)
        count_for_symbol = (
            select(func.count(func.distinct(FormulaToken.formula_id)))
            .where(FormulaToken.symbol_id == Symbol.id)
            .scalar_subquery()
        )
        self._session.execute(
            update(Symbol).values(usage_count=count_for_symbol)
        )
        self._session.flush()

    def list_by_type(self, symbol_type_id: int) -> list[Symbol]:
        self.get_symbol_type(symbol_type_id)
        return list(
            self._session.scalars(
                select(Symbol)
                .where(Symbol.symbol_type_id == symbol_type_id)
                .order_by(Symbol.id)
            )
        )

    def list_all(self) -> list[Symbol]:
        return list(self._session.scalars(select(Symbol).order_by(Symbol.id)))

    def list_aliases(self) -> list[SymbolAlias]:
        return list(
            self._session.scalars(
                select(SymbolAlias).order_by(
                    utf8_sort_key(SymbolAlias.alias), SymbolAlias.id
                )
            )
        )

    def add_alias(self, symbol_id: int, alias: str, source: str = "user") -> SymbolAlias:
        self.get(symbol_id)
        alias = alias.strip()
        if not alias:
            raise ValidationError("alias must not be empty")
        if source not in {"builtin", "user"}:
            raise ValidationError("alias source must be 'builtin' or 'user'")
        if self._session.scalar(select(Symbol).where(Symbol.name == alias)) is not None:
            raise ConflictError(
                "SymbolAlias", "alias", alias, code="symbol.alias_collision"
            )
        existing = self._session.scalar(select(SymbolAlias).where(SymbolAlias.alias == alias))
        if existing is not None:
            if existing.symbol_id == symbol_id and existing.source == source:
                return existing
            raise ConflictError(
                "SymbolAlias", "alias", alias, code="symbol.alias_collision"
            )
        row = SymbolAlias(symbol_id=symbol_id, alias=alias, source=source)
        self._session.add(row)
        self._session.flush()
        return row

    def get_by_public_id(self, public_id: str) -> Symbol:
        row = self._session.scalar(select(Symbol).where(Symbol.public_id == public_id))
        if row is None:
            raise NotFoundError("Symbol", public_id)
        return row

    def set_notation(
        self,
        symbol_id: int,
        notation_kind: str,
        precedence: int | None = None,
    ) -> Symbol:
        symbol = self.get(symbol_id)
        self._validate_notation(notation_kind, precedence, symbol.arity)
        self._validate_display_uniqueness(
            symbol.name, symbol.symbol_type, symbol.arity, notation_kind,
            symbol.latex_template, namespace_id=symbol.namespace_id,
            exclude_symbol_id=symbol.id,
        )
        symbol.notation_kind = notation_kind
        symbol.precedence = precedence
        self._session.flush()
        return symbol

    def set_latex_template(self, symbol_id: int, latex_template: str | None) -> Symbol:
        symbol = self.get(symbol_id)
        latex_template = self._normalize_latex_template(latex_template)
        self._validate_display_uniqueness(
            symbol.name, symbol.symbol_type, symbol.arity, symbol.notation_kind,
            latex_template, namespace_id=symbol.namespace_id,
            exclude_symbol_id=symbol.id,
        )
        symbol.latex_template = latex_template
        self._session.flush()
        return symbol

    def get_by_role(self, role: str) -> Symbol:
        self._validate_role_name(role)
        row = self._session.scalar(select(SymbolRole).where(SymbolRole.role == role))
        if row is None:
            raise NotFoundError("SymbolRole", role)
        return row.symbol

    def assign_role(self, role: str, symbol_id: int) -> None:
        self._validate_role_name(role)
        symbol = self.get(symbol_id)
        self._validate_role_assignment(role, symbol)

        existing_role = self._session.scalar(select(SymbolRole).where(SymbolRole.role == role))
        if existing_role is not None:
            raise ConflictError("SymbolRole", "role", role)
        existing_symbol = self._session.scalar(
            select(SymbolRole).where(SymbolRole.symbol_id == symbol_id)
        )
        if existing_symbol is not None:
            raise ConflictError("SymbolRole", "symbol_id", str(symbol_id))

        self._session.add(SymbolRole(role=role, symbol_id=symbol_id))
        self._session.flush()

    def _validate_display_uniqueness(
        self, name: str, symbol_type: SymbolType, arity: int,
        notation_kind: str, latex_template: str | None,
        namespace_id: int,
        *, exclude_symbol_id: int | None = None,
    ) -> None:
        signature = shape_signature(name, symbol_type, arity, notation_kind, latex_template)
        for other in self._session.scalars(
            select(Symbol).where(Symbol.namespace_id == namespace_id)
        ):
            if other.id != exclude_symbol_id and symbol_shape(other) == signature:
                raise ConflictError(
                    "Symbol", "display", str(signature), code="symbol.display_collision",
                    details={"symbol_id": other.id, "symbol_name": other.name,
                             "shape": list(signature)},
                )

    def _validate_notation(
        self, notation_kind: str, precedence: int | None, arity: int
    ) -> None:
        if notation_kind not in VALID_NOTATION_KINDS:
            raise ValidationError(f"unknown notation_kind: {notation_kind}")
        if notation_kind == "infix":
            if arity != 2:
                raise ValidationError("infix notation requires arity 2")
            if precedence is None:
                raise ValidationError("infix notation requires precedence")
        elif precedence is not None:
            raise ValidationError("precedence must be omitted for prefix notation")

    def _normalize_latex_template(self, latex_template: str | None) -> str | None:
        if latex_template is None:
            return None
        stripped = latex_template.strip()
        return stripped or None

    def _validate_role_name(self, role: str) -> None:
        if role not in VALID_ROLES:
            raise ValidationError(f"unknown role: {role}")

    def _validate_role_assignment(self, role: str, symbol: Symbol) -> None:
        required_type, required_arity = ROLE_REQUIREMENTS[role]
        try:
            actual_type = SymbolTypeName(symbol.symbol_type.name)
        except ValueError as exc:
            raise ValidationError(f"unknown SymbolType: {symbol.symbol_type.name}") from exc
        if actual_type != required_type or symbol.arity != required_arity:
            raise ValidationError(
                f"role {role!r} requires {required_type.value} arity {required_arity}"
            )
