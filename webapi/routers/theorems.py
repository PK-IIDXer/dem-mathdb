from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import exists, select

from dem.api import DemServices
from dem.db.models.theorem import Theorem
from dem.db.models.theorem import Proof
from dem.db.models.tag import Tag, TheoremTag
from dem.errors import ValidationError
from webapi.deps import dem_services
from webapi.pagination import Cursor, Limit, named_query, read_page
from webapi.schemas import (
    DescriptionUpdate,
    ApplicableTheoremOut,
    FormulaOut,
    TagAttach,
    TheoremCreate,
    TheoremOut,
    TheoremPremiseOut,
)

router = APIRouter(tags=["theorems"])
RULE_TAG = "system:rule"


def _has_verified_proof(dem: DemServices, theorem_id: int) -> bool:
    return bool(dem.session.scalar(select(exists().where(
        Proof.theorem_id == theorem_id, Proof.status == "verified"
    ))))


def _check_rule_tag(dem: DemServices, theorem_id: int, tag_id: int) -> None:
    if dem.session.scalar(select(Tag.name).where(Tag.id == tag_id)) == RULE_TAG:
        theorem = dem.theorems.get(theorem_id)
        if theorem.status != "proven" or not _has_verified_proof(dem, theorem_id):
            raise ValidationError("system:rule requires a proven theorem with a verified proof")


@router.get("/theorems/rules", response_model=list[TheoremOut])
def list_rule_theorems(dem: DemServices = Depends(dem_services)) -> list[TheoremOut]:
    """Resolve the display marker against current proof state on every request."""
    stmt = (
        select(Theorem)
        .join(TheoremTag, TheoremTag.theorem_id == Theorem.id)
        .join(Tag, Tag.id == TheoremTag.tag_id)
        .where(Tag.name == RULE_TAG, Theorem.status == "proven")
        .where(exists(select(Proof.id).where(
            Proof.theorem_id == Theorem.id, Proof.status == "verified"
        )))
        .order_by(Theorem.id)
    )
    return [
        theorem for theorem in dem.session.scalars(stmt)
        if all(tag.name != "system:onboarding" for tag in theorem.tags)
    ]


@router.get("/theorems/applicable", response_model=list[ApplicableTheoremOut])
def list_applicable_theorems(
    goal_formula_id: int | None = None,
    proof_id: int | None = None,
    arg_step_ords: list[str] | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    dem: DemServices = Depends(dem_services),
) -> list[ApplicableTheoremOut]:
    parsed_arg_ords: list[int] = []
    for value in arg_step_ords or []:
        try:
            parsed_arg_ords.extend(
                int(item.strip()) for item in value.split(",") if item.strip()
            )
        except ValueError as exc:
            raise ValidationError("arg_step_ords must contain integers") from exc
    return [
        ApplicableTheoremOut(
            theorem=TheoremOut.model_validate(theorem, from_attributes=True),
            is_schematic=is_schematic,
            score=score,
        )
        for theorem, is_schematic, score in dem.theorems.list_applicable(
            goal_formula_id,
            limit,
            proof_id=proof_id,
            arg_step_ords=parsed_arg_ords,
        )
    ]


@router.get("/theorems", response_model=list[TheoremOut])
def list_theorems(
    response: Response,
    search: str | None = None,
    tag_id: list[int] | None = Query(default=None),
    exclude_tag_id: list[int] | None = Query(default=None),
    status: str | None = None,
    dem: DemServices = Depends(dem_services),
    limit: Limit = None,
    cursor: Cursor = None,
) -> list[TheoremOut]:
    if limit is None and cursor is None and not exclude_tag_id:
        return dem.theorems.list_all(search=search, tag_ids=tag_id, status=status)
    stmt = named_query(Theorem, search, tag_id, exclude_tag_id)
    if status:
        stmt = stmt.where(Theorem.status == status)
    return read_page(dem.session, Theorem, stmt, response, limit, cursor)


@router.post("/theorems", response_model=TheoremOut, status_code=status.HTTP_201_CREATED)
def register_theorem(body: TheoremCreate, dem: DemServices = Depends(dem_services)) -> TheoremOut:
    theorem = dem.theorems.register(
        name=body.name,
        conclusion_formula_id=body.conclusion_formula_id,
        premise_formula_ids=body.premise_formula_ids,
        description=body.description,
        remarks=body.remarks,
    )
    for tag_id in body.tag_ids:
        _check_rule_tag(dem, theorem.id, tag_id)
        dem.tags.attach("theorem", theorem.id, tag_id)
    return theorem


@router.patch("/theorems/{id}/description", response_model=TheoremOut)
def update_theorem_description(
    id: int, body: DescriptionUpdate, dem: DemServices = Depends(dem_services)
) -> TheoremOut:
    return dem.theorems.set_description(id, body.description)


@router.post("/theorems/{id}/tags", response_model=TheoremOut)
def add_theorem_tag(
    id: int, body: TagAttach, dem: DemServices = Depends(dem_services)
) -> TheoremOut:
    _check_rule_tag(dem, id, body.tag_id)
    dem.tags.attach("theorem", id, body.tag_id)
    return dem.theorems.get(id)


@router.delete("/theorems/{id}/tags/{tag_id}", response_model=TheoremOut)
def remove_theorem_tag(
    id: int, tag_id: int, dem: DemServices = Depends(dem_services)
) -> TheoremOut:
    dem.tags.detach("theorem", id, tag_id)
    return dem.theorems.get(id)


@router.get("/theorems/by-name/{name}", response_model=TheoremOut)
def get_theorem_by_name(name: str, dem: DemServices = Depends(dem_services)) -> TheoremOut:
    return dem.theorems.get_by_name(name)


@router.get("/theorems/{ref}", response_model=TheoremOut)
def get_theorem(ref: str, dem: DemServices = Depends(dem_services)) -> TheoremOut:
    return (
        dem.theorems.get(int(ref))
        if ref.isdigit()
        else dem.theorems.get_by_public_id(ref)
    )


@router.get("/theorems/public/{public_id}", response_model=TheoremOut)
def get_theorem_by_public_id(
    public_id: str, dem: DemServices = Depends(dem_services)
) -> TheoremOut:
    return dem.theorems.get_by_public_id(public_id)


@router.get("/theorems/{id}/premises", response_model=list[TheoremPremiseOut])
def list_theorem_premises(
    id: int, dem: DemServices = Depends(dem_services)
) -> list[TheoremPremiseOut]:
    # list_premises() returns list[tuple[ord, Formula]]; a plain tuple has no
    # named attributes for from_attributes-style coercion, so each item is
    # converted explicitly rather than relying on FastAPI's response_model.
    return [
        TheoremPremiseOut(ord=ord_, formula=FormulaOut.model_validate(formula, from_attributes=True))
        for ord_, formula in dem.theorems.list_premises(id)
    ]


@router.get("/theorems/{id}/used-in-theorems", response_model=list[TheoremOut])
def list_theorem_used_in_theorems(
    id: int, dem: DemServices = Depends(dem_services)
) -> list[TheoremOut]:
    return dem.theorems.list_used_in_theorems(id)
