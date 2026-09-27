from __future__ import annotations

import hashlib
from collections.abc import Sequence

from sqlalchemy import bindparam, event, func, insert, select, update
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, SessionTransaction, joinedload

from dem.db.models.language import Formula, FormulaToken, FormulaType, Symbol, SymbolAlias, SymbolType
from dem.errors import FormulaValidationError, NotFoundError, ValidationError
from dem.services.authoring_provenance import AuthoringVia, record_authoring_provenance
from dem.identity import deterministic_public_id
from dem.types import FormulaTypeName, SymbolMeta, SymbolTypeName, Token
from demlang.match import MatchResult, match_formula


_PENDING_SYMBOL_USAGE_KEY = "_pending_symbol_usage_counts"


def flush_pending_symbol_usage_counts(
    session: Session, *, connection: Connection | None = None
) -> None:
    """Persist per-transaction formula usage deltas in one executemany call."""
    pending: dict[int, int] | None = session.info.get(_PENDING_SYMBOL_USAGE_KEY)
    if not pending:
        return
    statement = (
        update(Symbol.__table__)
        .where(Symbol.__table__.c.id == bindparam("usage_symbol_id"))
        .values(
            usage_count=(
                Symbol.__table__.c.usage_count + bindparam("usage_count_delta")
            )
        )
    )
    (connection or session.connection()).execute(
        statement,
        [
            {"usage_symbol_id": symbol_id, "usage_count_delta": delta}
            for symbol_id, delta in pending.items()
        ],
    )
    session.info.pop(_PENDING_SYMBOL_USAGE_KEY, None)
    for instance in list(session.identity_map.values()):
        if isinstance(instance, Symbol) and instance.id in pending:
            session.expire(instance, ["usage_count"])


@event.listens_for(Session, "before_commit")
def _flush_symbol_usage_before_commit(session: Session) -> None:
    flush_pending_symbol_usage_counts(session)


@event.listens_for(Session, "after_transaction_create")
def _flush_symbol_usage_before_savepoint(
    session: Session, transaction: SessionTransaction
) -> None:
    """Move outer pending deltas to the DB before a SAVEPOINT starts.

    ``after_transaction_create`` runs before the nested transaction acquires a
    connection. Executing through its parent therefore remains in the outer
    transaction and survives a rollback of the new savepoint.
    """
    if not transaction.nested or not session.info.get(_PENDING_SYMBOL_USAGE_KEY):
        return
    parent = transaction.parent
    if parent is None:
        return
    flush_pending_symbol_usage_counts(
        session, connection=parent.connection(None)
    )


@event.listens_for(Session, "after_rollback")
def _discard_symbol_usage_after_rollback(session: Session) -> None:
    session.info.pop(_PENDING_SYMBOL_USAGE_KEY, None)


def canonical_form(tokens: Sequence[Token], symbol_public_ids: dict[int, str]) -> str:
    parts: list[str] = []
    for token in tokens:
        if token.is_symbol:
            symbol_id = token.symbol_id
            if symbol_id is None or symbol_id not in symbol_public_ids:
                raise ValueError(f"missing public id for symbol {symbol_id}")
            parts.append(f"S{symbol_public_ids[symbol_id]};")
        else:
            parts.append(f"B{token.de_bruijn_index};")
    return "".join(parts)


def compute_hash(tokens: Sequence[Token], symbol_public_ids: dict[int, str]) -> str:
    return hashlib.sha256(canonical_form(tokens, symbol_public_ids).encode()).hexdigest()


def validate_tokens(
    tokens: Sequence[Token],
    symbol_meta: dict[int, SymbolMeta],
) -> FormulaTypeName:
    """Validate a token sequence against the Phase 1 formula construction rules."""

    if not tokens:
        raise FormulaValidationError("empty token list", code="formula.empty")

    next_pos, formula_type = _parse(tokens, 0, 0, symbol_meta, expected_type=None)
    if next_pos != len(tokens):
        raise FormulaValidationError(f"trailing tokens at position {next_pos}", next_pos, code="formula.trailing_tokens")
    return formula_type


def _parse(
    tokens: Sequence[Token],
    pos: int,
    scope_depth: int,
    symbol_meta: dict[int, SymbolMeta],
    expected_type: FormulaTypeName | None,
) -> tuple[int, FormulaTypeName]:
    if pos >= len(tokens):
        raise FormulaValidationError("unexpected end of tokens", code="formula.unexpected_end")

    token = tokens[pos]
    if token.is_bound_var:
        index = _bound_index(token)
        if index >= scope_depth:
            raise FormulaValidationError(
                f"unbound de Bruijn index {index} (scope depth {scope_depth})",
                pos, code="formula.unbound_variable")
        produced_type = FormulaTypeName.TERM
        _ensure_expected_type(expected_type, produced_type, pos)
        return pos + 1, produced_type

    meta = symbol_meta[_symbol_id(token)]
    produced_type = meta.output_formula_type
    _ensure_expected_type(expected_type, produced_type, pos)

    if meta.symbol_type_name == SymbolTypeName.FREE_PROP_VAR:
        cur_pos = pos + 1
        for _ in range(meta.arity):
            cur_pos, _ = _parse(
                tokens,
                cur_pos,
                scope_depth,
                symbol_meta,
                expected_type=FormulaTypeName.TERM,
            )
        return cur_pos, produced_type

    if meta.is_quantifier:
        if meta.arity != 1:
            raise FormulaValidationError("quantifier symbol must have arity 1", pos, code="formula.quantifier_arity")
        next_pos, _ = _parse(
            tokens,
            pos + 1,
            scope_depth + 1,
            symbol_meta,
            expected_type=FormulaTypeName.PROPOSITION,
        )
        return next_pos, produced_type

    if meta.arity == 0:
        return pos + 1, produced_type
    if meta.input_formula_type is None:
        raise FormulaValidationError("symbol cannot take arguments", pos, code="formula.not_applicable")

    cur_pos = pos + 1
    for _ in range(meta.arity):
        cur_pos, _ = _parse(
            tokens,
            cur_pos,
            scope_depth,
            symbol_meta,
            expected_type=meta.input_formula_type,
        )
    return cur_pos, produced_type

def _ensure_expected_type(
    expected_type: FormulaTypeName | None,
    produced_type: FormulaTypeName,
    pos: int,
) -> None:
    if expected_type is not None and produced_type != expected_type:
        raise FormulaValidationError(
            f"expected {expected_type.value} but got {produced_type.value} at position {pos}",
            pos, code="formula.type_mismatch")


def _symbol_id(token: Token) -> int:
    if token.symbol_id is None:
        raise AssertionError("token is not a symbol")
    return token.symbol_id


def _bound_index(token: Token) -> int:
    if token.de_bruijn_index is None:
        raise AssertionError("token is not a bound variable")
    return token.de_bruijn_index


class FormulaService:
    def __init__(
        self,
        session: Session,
        *,
        authoring_via: AuthoringVia | None = None,
    ) -> None:
        self._session = session
        self._authoring_via = authoring_via

    def validate(self, tokens: list[Token]) -> None:
        symbol_meta = self._load_symbol_meta(tokens)
        validate_tokens(tokens, symbol_meta)

    def parse_text(
        self, text: str, context: dict[str, int] | None = None
    ) -> tuple[list[Token], int | None]:
        from demlang import DemlangSyntaxError, parse_convenience

        try:
            tokens = parse_convenience(text, self.surface_symbol_table(), context)
        except DemlangSyntaxError as exc:
            details: dict[str, object] = {"position": exc.position}
            if exc.expected_type is not None:
                details["expected_type"] = exc.expected_type.value
            raise FormulaValidationError(
                str(exc), exc.position, code=exc.code or "formula.syntax_error", details=details
            ) from exc
        validate_tokens(tokens, self._load_symbol_meta(tokens))
        existing_id = self._session.scalar(
            select(Formula.id).where(
                Formula.hash == compute_hash(tokens, self._load_symbol_public_ids(tokens))
            )
        )
        return tokens, existing_id

    def print_text(self, tokens: list[Token]) -> str:
        from demlang import print_dss

        validate_tokens(tokens, self._load_symbol_meta(tokens))
        return print_dss(tokens, self.surface_symbol_table())

    def search(
        self,
        pattern: list[Token],
        *,
        limit: int = 50,
        after_id: int | None = None,
    ) -> list[tuple[int, MatchResult]]:
        """Return at most ``limit + 1`` structural matches in formula-ID order."""
        pattern_meta = self._load_symbol_meta(pattern)
        schema_types = {
            SymbolTypeName.FREE_TERM_VAR,
            SymbolTypeName.FREE_PROP_VAR,
        }
        fixed_symbol_ids = sorted(
            {
                token.symbol_id
                for token in pattern
                if token.symbol_id is not None
                and pattern_meta[token.symbol_id].symbol_type_name not in schema_types
            }
        )
        root_symbol_id = pattern[0].symbol_id
        root_is_fixed = root_symbol_id in fixed_symbol_ids
        if root_is_fixed:
            base = (
                select(Formula.id)
                .join(
                    FormulaToken,
                    (FormulaToken.formula_id == Formula.id)
                    & (FormulaToken.position == 0),
                )
                .where(FormulaToken.symbol_id == root_symbol_id)
            )
        else:
            base = select(Formula.id)
        # A schema symbol at the root can absorb its entire argument tree (and
        # report an undetermined higher-order binding), so nested fixed symbols
        # are not guaranteed to occur in the target.  Filtering on them would
        # create false negatives.  A fixed root, by contrast, makes every
        # remaining fixed symbol structurally mandatory.
        remaining_ids = (
            [
                symbol_id
                for symbol_id in fixed_symbol_ids
                if symbol_id != root_symbol_id
            ]
            if root_is_fixed
            else []
        )
        if remaining_ids:
            candidates_with_fixed_symbols = (
                select(FormulaToken.formula_id)
                .where(FormulaToken.symbol_id.in_(remaining_ids))
                .group_by(FormulaToken.formula_id)
                .having(
                    func.count(func.distinct(FormulaToken.symbol_id))
                    == len(remaining_ids)
                )
            )
            base = base.where(Formula.id.in_(candidates_with_fixed_symbols))

        matches: list[tuple[int, MatchResult]] = []
        last_id = after_id or 0
        # Stay below SQLite's host-parameter ceiling even for internal callers
        # that request an exhaustive scan rather than an HTTP-sized page.
        batch_size = min(500, max(256, (limit + 1) * 8))
        while len(matches) <= limit:
            candidate_ids = list(
                self._session.scalars(
                    base.where(Formula.id > last_id)
                    .order_by(Formula.id)
                    .limit(batch_size)
                )
            )
            if not candidate_ids:
                break
            last_id = candidate_ids[-1]
            rows = self._session.execute(
                select(
                    FormulaToken.formula_id,
                    FormulaToken.symbol_id,
                    FormulaToken.de_bruijn_index,
                )
                .where(FormulaToken.formula_id.in_(candidate_ids))
                .order_by(FormulaToken.formula_id, FormulaToken.position)
            )
            tokens_by_formula: dict[int, list[Token]] = {
                formula_id: [] for formula_id in candidate_ids
            }
            for formula_id, symbol_id, de_bruijn_index in rows:
                tokens_by_formula[formula_id].append(
                    Token(symbol_id=symbol_id, de_bruijn_index=de_bruijn_index)
                )
            all_tokens = [
                token
                for formula_tokens in tokens_by_formula.values()
                for token in formula_tokens
            ]
            symbol_meta = self._load_symbol_meta([*pattern, *all_tokens])
            for formula_id in candidate_ids:
                matched = match_formula(
                    pattern, tokens_by_formula[formula_id], symbol_meta
                )
                if matched is not None:
                    matches.append((formula_id, matched))
                    if len(matches) > limit:
                        break
            if len(candidate_ids) < batch_size:
                break
        return matches

    def surface_symbol_table(self):
        """Return a DB-independent snapshot used by :mod:`demlang`."""
        from demlang import SurfaceSymbol, SymbolTable

        symbols = list(
            self._session.scalars(
                select(Symbol).options(
                    joinedload(Symbol.symbol_type).joinedload(SymbolType.output_formula_type),
                    joinedload(Symbol.symbol_type).joinedload(SymbolType.input_formula_type),
                )
            )
        )
        aliases = {
            row.alias: row.symbol_id for row in self._session.scalars(select(SymbolAlias))
        }
        return SymbolTable(
            symbols={
                symbol.id: SurfaceSymbol(
                    id=symbol.id,
                    name=symbol.name,
                    namespace=symbol.namespace.name,
                    meta=self._symbol_to_meta(symbol),
                    notation_kind=symbol.notation_kind,
                    precedence=symbol.precedence,
                )
                for symbol in symbols
            },
            aliases=aliases,
        )

    def register(self, tokens: list[Token], remarks: str | None = None) -> Formula:
        formula_hash = compute_hash(tokens, self._load_symbol_public_ids(tokens))
        cache = self._session.info.setdefault("_formula_hash_cache", {})
        cached = cache.get(formula_hash)
        if cached is not None:
            return cached

        symbol_meta = self._load_symbol_meta(tokens)
        formula_type_name = validate_tokens(tokens, symbol_meta)

        existing = self._session.scalar(select(Formula).where(Formula.hash == formula_hash))
        if existing is not None:
            cache[formula_hash] = existing
            return existing

        formula_type_cache: dict[str, FormulaType] = self._session.info.setdefault(
            "_formula_type_cache", {}
        )
        formula_type = formula_type_cache.get(formula_type_name.value)
        if formula_type is None:
            formula_type = self._session.scalar(
                select(FormulaType).where(FormulaType.name == formula_type_name.value)
            )
        if formula_type is None:
            raise NotFoundError("FormulaType", formula_type_name.value)
        formula_type_cache[formula_type_name.value] = formula_type

        formula = Formula(
            public_id=deterministic_public_id("formula", formula_hash),
            formula_type_id=formula_type.id,
            hash=formula_hash,
            token_count=len(tokens),
            remarks=remarks,
        )
        self._session.add(formula)
        self._session.flush()
        record_authoring_provenance(
            self._session,
            entity_kind="formula",
            entity_id=formula.id,
            via=self._authoring_via,
        )

        self._session.execute(
            insert(FormulaToken).execution_options(render_nulls=True),
            [
                {
                    "formula_id": formula.id,
                    "position": position,
                    "symbol_id": token.symbol_id,
                    "de_bruijn_index": token.de_bruijn_index,
                }
                for position, token in enumerate(tokens)
            ],
        )
        used_symbol_ids = {
            token.symbol_id for token in tokens if token.symbol_id is not None
        }
        pending_usage: dict[int, int] = self._session.info.setdefault(
            _PENDING_SYMBOL_USAGE_KEY, {}
        )
        for symbol_id in used_symbol_ids:
            pending_usage[symbol_id] = pending_usage.get(symbol_id, 0) + 1
        cache[formula_hash] = formula
        return formula

    def _load_symbol_public_ids(self, tokens: Sequence[Token]) -> dict[int, str]:
        symbol_ids = {token.symbol_id for token in tokens if token.symbol_id is not None}
        cache: dict[int, str] = self._session.info.setdefault(
            "_symbol_public_id_cache", {}
        )
        missing = symbol_ids - cache.keys()
        if missing:
            cache.update(
                self._session.execute(
                    select(Symbol.id, Symbol.public_id).where(Symbol.id.in_(missing))
                ).all()
            )
        absent = symbol_ids - cache.keys()
        if absent:
            raise NotFoundError("Symbol", min(absent))
        return {symbol_id: cache[symbol_id] for symbol_id in symbol_ids}

    def get(self, id: int) -> Formula:
        row = self._session.get(Formula, id)
        if row is None:
            raise NotFoundError("Formula", id)
        return row

    def get_by_public_id(self, public_id: str) -> Formula:
        row = self._session.scalar(select(Formula).where(Formula.public_id == public_id))
        if row is None:
            raise NotFoundError("Formula", public_id)
        return row

    def get_by_hash(self, hash: str) -> Formula:
        row = self._session.scalar(select(Formula).where(Formula.hash == hash))
        if row is None:
            raise NotFoundError("Formula", hash)
        return row

    def get_tokens(self, formula_id: int) -> list[FormulaToken]:
        cache = self._session.info.setdefault("_formula_tokens_cache", {})
        cached = cache.get(formula_id)
        if cached is not None:
            return cached
        self.get(formula_id)
        rows = list(
            self._session.scalars(
                select(FormulaToken)
                .where(FormulaToken.formula_id == formula_id)
                .order_by(FormulaToken.position)
            )
        )
        cache[formula_id] = rows
        return rows

    def _load_symbol_meta(self, tokens: Sequence[Token]) -> dict[int, SymbolMeta]:
        symbol_ids = {token.symbol_id for token in tokens if token.symbol_id is not None}
        if not symbol_ids:
            return {}

        cache: dict[int, SymbolMeta] = self._session.info.setdefault("_symbol_meta_cache", {})
        missing_from_cache = symbol_ids - cache.keys()
        if missing_from_cache:
            symbols = list(
                self._session.scalars(
                    select(Symbol)
                    .options(
                        joinedload(Symbol.symbol_type).joinedload(SymbolType.output_formula_type),
                        joinedload(Symbol.symbol_type).joinedload(SymbolType.input_formula_type),
                    )
                    .where(Symbol.id.in_(missing_from_cache))
                )
            )
            found_ids = {symbol.id for symbol in symbols}
            missing_ids = sorted(missing_from_cache - found_ids)
            if missing_ids:
                raise NotFoundError("Symbol", missing_ids[0])
            for symbol in symbols:
                cache[symbol.id] = self._symbol_to_meta(symbol)

        return {sid: cache[sid] for sid in symbol_ids}

    def _symbol_to_meta(self, symbol: Symbol) -> SymbolMeta:
        symbol_type = symbol.symbol_type
        try:
            symbol_type_name = SymbolTypeName(symbol_type.name)
            output_type = FormulaTypeName(symbol_type.output_formula_type.name)
            input_type = (
                FormulaTypeName(symbol_type.input_formula_type.name)
                if symbol_type.input_formula_type is not None
                else None
            )
        except ValueError as exc:
            raise ValidationError("seed data contains unknown formula or symbol type") from exc

        return SymbolMeta(
            arity=symbol.arity,
            symbol_type_name=symbol_type_name,
            output_formula_type=output_type,
            input_formula_type=input_type,
            is_quantifier=symbol_type.is_quantifier,
        )
