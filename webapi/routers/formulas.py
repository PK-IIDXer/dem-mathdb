from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import Session

from dem.api import DemServices
from dem.types import FormulaTypeName
from dem.db.models.language import Formula, FormulaToken, FormulaType
from dem.db.models.inference import Axiom
from dem.db.models.theorem import Theorem
from webapi.deps import dem_services
from webapi.pagination import Cursor, Limit, decode_cursor, encode_cursor, read_page
from webapi.schemas import (
    FormulaCreate,
    FormulaDetailOut,
    FormulaOut,
    FormulaParseOut,
    FormulaParseRequest,
    FormulaPrintOut,
    FormulaPrintRequest,
    FormulaSearchOut,
    FormulaSearchRequest,
    FormulaTypeOut,
    FormulaValidateRequest,
    NamedConclusionsOut,
    TokenOut,
)

router = APIRouter(tags=["formulas"])


@router.get("/formulas/{id}/named-conclusions", response_model=NamedConclusionsOut)
def named_conclusions(id: int, dem: DemServices = Depends(dem_services)) -> NamedConclusionsOut:
    """Names whose stored conclusion is exactly this formula, for display only."""
    dem.formulas.get(id)  # Preserve the ordinary formula lookup's 404 behavior.
    axioms = dem.session.scalars(select(Axiom).where(Axiom.formula_id == id).order_by(Axiom.id))
    theorems = dem.session.scalars(
        select(Theorem).where(Theorem.conclusion_formula_id == id).order_by(Theorem.id)
    )
    return NamedConclusionsOut(
        axioms=[{"public_id": item.public_id, "name": item.name, "description": item.description} for item in axioms],
        theorems=[{"public_id": item.public_id, "name": item.name, "description": item.description} for item in theorems],
    )


@router.post("/formulas/search", response_model=FormulaSearchOut)
def search_formulas(
    body: FormulaSearchRequest, dem: DemServices = Depends(dem_services)
) -> FormulaSearchOut:
    pattern, _ = dem.formulas.parse_text(body.pattern, body.context)
    matches = dem.formulas.search(
        pattern,
        limit=body.limit,
        after_id=decode_cursor(body.cursor) if body.cursor is not None else None,
    )
    has_more = len(matches) > body.limit
    page = matches[: body.limit]
    table = dem.formulas.surface_symbol_table()
    items = []
    for formula_id, matched in page:
        bindings = {
            table.spelling(symbol_id): {
                "kind": "term",
                "tokens": [
                    {"symbol_id": token.symbol_id, "de_bruijn_index": token.de_bruijn_index}
                    for token in tokens
                ],
            }
            for symbol_id, tokens in matched.term_substs.items()
        }
        bindings.update(
            {
                table.spelling(symbol_id): {
                    "kind": "proposition",
                    "tokens": [
                        {"symbol_id": token.symbol_id, "de_bruijn_index": token.de_bruijn_index}
                        for token in binding.body_tokens
                    ],
                    "parameter_de_bruijn_index": binding.parameter_de_bruijn_index,
                }
                for symbol_id, binding in matched.prop_substs.items()
            }
        )
        items.append({"formula_id": formula_id, "bindings": bindings})
    return FormulaSearchOut(
        items=items,
        next_cursor=encode_cursor(page[-1][0]) if has_more and page else None,
    )


@router.post("/formulas/parse", response_model=FormulaParseOut)
def parse_formula(
    body: FormulaParseRequest, dem: DemServices = Depends(dem_services)
) -> FormulaParseOut:
    tokens, formula_id = dem.formulas.parse_text(body.text, body.context)
    return FormulaParseOut(
        tokens=[
            {"symbol_id": token.symbol_id, "de_bruijn_index": token.de_bruijn_index}
            for token in tokens
        ],
        formula_id=formula_id,
    )


@router.post("/formulas/print", response_model=FormulaPrintOut)
def print_formula(
    body: FormulaPrintRequest, dem: DemServices = Depends(dem_services)
) -> FormulaPrintOut:
    return FormulaPrintOut(
        text=dem.formulas.print_text([token.to_domain() for token in body.tokens])
    )


def formula_detail(formula: Formula, tokens: list[FormulaToken]) -> FormulaDetailOut:
    """One formula with its tokens. Shared with the proofs router's bulk read."""
    # Formula.tokens uses lazy="raise" (see language.py), so we never touch that
    # relationship here; token rows are fetched explicitly via get_tokens() instead
    # and merged in after validating the scalar fields.
    base = FormulaOut.model_validate(formula, from_attributes=True)
    token_outs = [TokenOut.model_validate(row, from_attributes=True) for row in tokens]
    return FormulaDetailOut(**base.model_dump(), tokens=token_outs)


def formula_details(session: Session, formula_ids: Iterable[int] | ColumnElement) -> list[FormulaDetailOut]:
    """Formulas with their tokens in two queries, ordered by formula id.

    `formula_ids` is either the ids themselves or a scalar subquery selecting them.
    `Formula.tokens` is lazy="raise" (see language.py), so the token rows are
    grouped here by hand rather than one `get_tokens()` per formula.
    """
    if not isinstance(formula_ids, ColumnElement):
        formula_ids = list(formula_ids)
    # This bulk path is intentionally row-based. A large proof returns many
    # formulas and tokens; constructing a
    # SQLAlchemy identity-map entry for every token dominated the endpoint even
    # though the database work itself was small.  These columns are constrained
    # database values and exactly mirror the response models, so model_construct
    # avoids validating the same trusted values twice (here and at the FastAPI
    # response boundary).
    formula_rows = session.execute(
        select(
            Formula.id,
            Formula.public_id,
            Formula.formula_type_id,
            Formula.hash,
            Formula.token_count,
            Formula.description,
            Formula.remarks,
            Formula.created_at,
            FormulaType.id.label("type_id"),
            FormulaType.name.label("type_name"),
            FormulaType.code.label("type_code"),
            FormulaType.remarks.label("type_remarks"),
            FormulaType.created_at.label("type_created_at"),
        )
        .join(FormulaType, FormulaType.id == Formula.formula_type_id)
        .where(Formula.id.in_(formula_ids))
        .order_by(Formula.id)
    ).all()
    tokens_by_formula: dict[int, list[TokenOut]] = {}
    for formula_id, position, symbol_id, de_bruijn_index in session.execute(
        select(
            FormulaToken.formula_id,
            FormulaToken.position,
            FormulaToken.symbol_id,
            FormulaToken.de_bruijn_index,
        )
        .where(FormulaToken.formula_id.in_(formula_ids))
        .order_by(FormulaToken.formula_id, FormulaToken.position)
    ):
        tokens_by_formula.setdefault(formula_id, []).append(
            TokenOut.model_construct(
                position=position,
                symbol_id=symbol_id,
                de_bruijn_index=de_bruijn_index,
            )
        )
    return [
        FormulaDetailOut.model_construct(
            id=row.id,
            public_id=row.public_id,
            formula_type_id=row.formula_type_id,
            formula_type=FormulaTypeOut.model_construct(
                id=row.type_id,
                name=row.type_name,
                code=row.type_code,
                remarks=row.type_remarks,
                created_at=row.type_created_at,
            ),
            hash=row.hash,
            token_count=row.token_count,
            description=row.description,
            remarks=row.remarks,
            created_at=row.created_at,
            tokens=tokens_by_formula.get(row.id, []),
        )
        for row in formula_rows
    ]


@router.post("/formulas/validate")
def validate_formula(
    body: FormulaValidateRequest, dem: DemServices = Depends(dem_services)
) -> dict[str, bool]:
    dem.formulas.validate([token.to_domain() for token in body.tokens])
    return {"valid": True}


@router.post("/formulas", response_model=FormulaDetailOut, status_code=status.HTTP_201_CREATED)
def register_formula(
    body: FormulaCreate, dem: DemServices = Depends(dem_services)
) -> FormulaDetailOut:
    formula = dem.formulas.register(
        [token.to_domain() for token in body.tokens], remarks=body.remarks
    )
    return formula_detail(formula, dem.formulas.get_tokens(formula.id))


@router.get("/formulas", response_model=list[FormulaOut])
def list_formulas(
    response: Response,
    dem: DemServices = Depends(dem_services),
    limit: Limit = None,
    cursor: Cursor = None,
    type: Literal["proposition", "term"] | None = None,
    head_symbol_id: Annotated[int | None, Query(ge=1)] = None,
    contains_symbol_id: Annotated[int | None, Query(ge=1)] = None,
) -> list[Formula]:
    # FormulaService has no bulk listing method (by design, see docs/design/api/formula-service.md);
    # this is a thin read-only query kept in the web layer rather than added to dem/.
    stmt = select(Formula)
    if type is not None:
        stmt = stmt.where(Formula.formula_type_id.in_(
            select(FormulaType.id).where(FormulaType.name == {
                "proposition": FormulaTypeName.PROPOSITION.value,
                "term": FormulaTypeName.TERM.value,
            }[type])
        ))
    if head_symbol_id is not None:
        stmt = stmt.where(select(FormulaToken.id).where(
            FormulaToken.formula_id == Formula.id,
            FormulaToken.position == 0,
            FormulaToken.symbol_id == head_symbol_id,
        ).exists())
    if contains_symbol_id is not None:
        stmt = stmt.where(select(FormulaToken.id).where(
            FormulaToken.formula_id == Formula.id,
            FormulaToken.symbol_id == contains_symbol_id,
        ).exists())
    return read_page(dem.session, Formula, stmt, response, limit, cursor)


BATCH_MAX_IDS = 500


# Declared before `/formulas/{ref}`, which would otherwise take "batch" as a public id.
@router.get("/formulas/batch", response_model=list[FormulaDetailOut])
def get_formulas_batch(
    ids: Annotated[str, Query(pattern=r"^[1-9]\d{0,17}(,[1-9]\d{0,17})*$")],
    dem: DemServices = Depends(dem_services),
) -> list[FormulaDetailOut]:
    """The given formulas with their tokens, e.g. `?ids=3,1,2`.

    Views that list many formulas (a theorem's premises, the theorem search
    results) would otherwise send one `GET /formulas/{id}` per formula. Ids are
    deduplicated and at most `BATCH_MAX_IDS` distinct ones are accepted. Unknown
    ids are left out rather than failing the whole read. Ordered by id, not by
    the order the ids were given.
    """
    formula_ids = set(map(int, ids.split(",")))
    if len(formula_ids) > BATCH_MAX_IDS:
        raise HTTPException(
            status_code=422, detail=f"At most {BATCH_MAX_IDS} distinct ids per request"
        )
    return formula_details(dem.session, formula_ids)


@router.get("/formulas/by-hash/{hash}", response_model=FormulaDetailOut)
def get_formula_by_hash(hash: str, dem: DemServices = Depends(dem_services)) -> FormulaDetailOut:
    formula = dem.formulas.get_by_hash(hash)
    return formula_detail(formula, dem.formulas.get_tokens(formula.id))


@router.get("/formulas/{ref}", response_model=FormulaDetailOut)
def get_formula(ref: str, dem: DemServices = Depends(dem_services)) -> FormulaDetailOut:
    formula = (
        dem.formulas.get(int(ref))
        if ref.isdigit()
        else dem.formulas.get_by_public_id(ref)
    )
    return formula_detail(formula, dem.formulas.get_tokens(formula.id))


@router.get("/formulas/public/{public_id}", response_model=FormulaDetailOut)
def get_formula_by_public_id(
    public_id: str, dem: DemServices = Depends(dem_services)
) -> FormulaDetailOut:
    formula = dem.formulas.get_by_public_id(public_id)
    return formula_detail(formula, dem.formulas.get_tokens(formula.id))
