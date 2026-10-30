from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import exists, func, select

from dem.api import DemServices
from dem.db.models.theorem import Theorem
from dem.db.models.theorem import Proof
from dem.db.models.tag import Tag, TheoremTag
from dem.errors import ValidationError
from dem.services.system_tags import EXPLORATION_TAG, HIDDEN_THEOREM_TAGS, visible_theorem_clause
from webapi.deps import dem_services, get_local_namespace_name
from webapi.pagination import Cursor, Limit, named_query, read_page
from webapi.presentation import displayed, visible_ids, visible_theorems
from webapi import beta
from webapi.schemas import (
    DescriptionUpdate,
    ExternalSourceOut,
    ApplicableTheoremOut,
    FormulaOut,
    TagAttach,
    TheoremCreate,
    TheoremOut,
    TheoremPremiseOut,
)
from webapi.theorem_output import external_sources, theorem_output, theorem_outputs

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
def list_rule_theorems(dem: DemServices = Depends(dem_services, scope="function")) -> list[TheoremOut]:
    """Resolve the display marker against current proof state on every request."""
    stmt = (
        select(Theorem)
        .join(TheoremTag, TheoremTag.theorem_id == Theorem.id)
        .join(Tag, Tag.id == TheoremTag.tag_id)
        .where(
            Tag.name == RULE_TAG,
            Theorem.status == "proven",
            visible_theorem_clause(Theorem.id, HIDDEN_THEOREM_TAGS),
        )
        .where(exists(select(Proof.id).where(
            Proof.theorem_id == Theorem.id, Proof.status == "verified"
        )))
        .order_by(Theorem.id)
    )
    theorems = list(dem.session.scalars(stmt))
    return theorem_outputs(dem.session, theorems)


@router.get("/theorems/applicable", response_model=list[ApplicableTheoremOut])
def list_applicable_theorems(
    goal_formula_id: int | None = None,
    proof_id: int | None = None,
    arg_step_ords: list[str] | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    dem: DemServices = Depends(dem_services, scope="function"),
) -> list[ApplicableTheoremOut]:
    parsed_arg_ords: list[int] = []
    for value in arg_step_ords or []:
        try:
            parsed_arg_ords.extend(
                int(item.strip()) for item in value.split(",") if item.strip()
            )
        except ValueError as exc:
            raise ValidationError("arg_step_ords must contain integers") from exc
    # The service ranks all matching rows already. Filter before the public
    # result limit so hidden rows cannot crowd visible candidates out.
    candidates = dem.theorems.list_applicable(
        goal_formula_id, dem.session.scalar(select(func.count()).select_from(Theorem)),
        proof_id=proof_id, arg_step_ords=parsed_arg_ords,
    )
    shown = visible_ids(dem.session, [item.id for item, _, _ in candidates])
    candidates = [entry for entry in candidates if entry[0].id in shown][:limit]
    return [
        ApplicableTheoremOut(
            theorem=theorem_output(dem.session, theorem),
            is_schematic=is_schematic,
            score=score,
        )
        for theorem, is_schematic, score in candidates
    ]


@router.get("/theorems", response_model=list[TheoremOut])
def list_theorems(
    response: Response,
    search: str | None = None,
    tag_id: list[int] | None = Query(default=None),
    exclude_tag_id: list[int] | None = Query(default=None),
    status: str | None = None,
    dem: DemServices = Depends(dem_services, scope="function"),
    limit: Limit = None,
    cursor: Cursor = None,
) -> list[TheoremOut]:
    if limit is None and cursor is None and not exclude_tag_id:
        return theorem_outputs(
            dem.session,
            displayed(dem.session, dem.theorems.list_all(search=search, tag_ids=tag_id, status=status)),
        )
    stmt = named_query(Theorem, search, tag_id, exclude_tag_id).where(
        visible_theorems()
    )
    if status:
        stmt = stmt.where(Theorem.status == status)
    return theorem_outputs(
        dem.session,
        read_page(dem.session, Theorem, stmt, response, limit, cursor),
    )


@router.post("/theorems", response_model=TheoremOut, status_code=status.HTTP_201_CREATED)
def register_theorem(
    body: TheoremCreate,
    dem: DemServices = Depends(dem_services, scope="function"),
    namespace: str = Depends(get_local_namespace_name, scope="function"),
) -> TheoremOut:
    theorem = dem.theorems.register(
        name=body.name,
        conclusion_formula_id=body.conclusion_formula_id,
        premise_formula_ids=body.premise_formula_ids,
        description=body.description,
        remarks=body.remarks,
        namespace=namespace,
    )
    for tag_id in body.tag_ids:
        if beta.enabled() and dem.session.scalar(select(Tag.name).where(Tag.id == tag_id)) == EXPLORATION_TAG:
            raise ValidationError("Create exploration notes through /explorations", code="beta.reserved_tag")
        _check_rule_tag(dem, theorem.id, tag_id)
        dem.tags.attach("theorem", theorem.id, tag_id)
    return theorem_output(dem.session, theorem)


@router.patch("/theorems/{id}/description", response_model=TheoremOut)
def update_theorem_description(
    id: int, body: DescriptionUpdate, dem: DemServices = Depends(dem_services, scope="function")
) -> TheoremOut:
    return theorem_output(dem.session, dem.theorems.set_description(id, body.description))


@router.post("/theorems/{id}/tags", response_model=TheoremOut)
def add_theorem_tag(
    id: int, body: TagAttach, dem: DemServices = Depends(dem_services, scope="function")
) -> TheoremOut:
    if beta.enabled():
        tag_name = dem.session.scalar(select(Tag.name).where(Tag.id == body.tag_id))
        attached = dem.session.get(TheoremTag, (id, body.tag_id))
        if tag_name in HIDDEN_THEOREM_TAGS and attached is None:
            raise ValidationError("Reserved visibility tags cannot be added to existing theorems in beta", code="beta.reserved_tag")
    _check_rule_tag(dem, id, body.tag_id)
    dem.tags.attach("theorem", id, body.tag_id)
    return theorem_output(dem.session, dem.theorems.get(id))


@router.delete("/theorems/{id}/tags/{tag_id}", response_model=TheoremOut)
def remove_theorem_tag(
    id: int, tag_id: int, dem: DemServices = Depends(dem_services, scope="function")
) -> TheoremOut:
    dem.tags.detach("theorem", id, tag_id)
    return theorem_output(dem.session, dem.theorems.get(id))


@router.get("/external-sources", response_model=list[ExternalSourceOut])
def list_external_sources(
    dem: DemServices = Depends(dem_services, scope="function"),
) -> list[ExternalSourceOut]:
    return external_sources(dem.session)


@router.get("/theorems/by-name/{name}", response_model=TheoremOut)
def get_theorem_by_name(name: str, dem: DemServices = Depends(dem_services, scope="function")) -> TheoremOut:
    return theorem_output(dem.session, dem.theorems.get_by_name(name))


@router.get("/theorems/{ref}", response_model=TheoremOut)
def get_theorem(ref: str, dem: DemServices = Depends(dem_services, scope="function")) -> TheoremOut:
    theorem = (
        dem.theorems.get(int(ref))
        if ref.isdigit()
        else dem.theorems.get_by_public_id(ref)
    )
    return theorem_output(dem.session, theorem)


@router.get("/theorems/public/{public_id}", response_model=TheoremOut)
def get_theorem_by_public_id(
    public_id: str, dem: DemServices = Depends(dem_services, scope="function")
) -> TheoremOut:
    return theorem_output(dem.session, dem.theorems.get_by_public_id(public_id))


@router.get("/theorems/{id}/premises", response_model=list[TheoremPremiseOut])
def list_theorem_premises(
    id: int, dem: DemServices = Depends(dem_services, scope="function")
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
    id: int, dem: DemServices = Depends(dem_services, scope="function")
) -> list[TheoremOut]:
    return theorem_outputs(dem.session, displayed(dem.session, dem.theorems.list_used_in_theorems(id)))
