from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from dem.api import DemServices
from dem.db.models.inference import Axiom
from webapi.deps import dem_services
from webapi.pagination import Cursor, Limit, named_query, read_page
from webapi.schemas import (
    AxiomCreate,
    AxiomOut,
    AxiomSystemCreate,
    AxiomSystemMemberAdd,
    AxiomSystemOut,
    DescriptionUpdate,
    IsSubsetOut,
    TagAttach,
    TheoremOut,
)

router = APIRouter(tags=["axioms"])


@router.get("/axioms", response_model=list[AxiomOut])
def list_axioms(
    response: Response,
    search: str | None = None,
    tag_id: list[int] | None = Query(default=None),
    exclude_tag_id: list[int] | None = Query(default=None),
    dem: DemServices = Depends(dem_services),
    limit: Limit = None,
    cursor: Cursor = None,
) -> list[AxiomOut]:
    if limit is None and cursor is None and not exclude_tag_id:
        return dem.axioms.list_axioms(search=search, tag_ids=tag_id)
    return read_page(
        dem.session,
        Axiom,
        named_query(Axiom, search, tag_id, exclude_tag_id),
        response,
        limit,
        cursor,
    )


@router.post("/axioms", response_model=AxiomOut, status_code=status.HTTP_201_CREATED)
def register_axiom(body: AxiomCreate, dem: DemServices = Depends(dem_services)) -> AxiomOut:
    return dem.axioms.register(
        name=body.name,
        formula_id=body.formula_id,
        description=body.description,
        remarks=body.remarks,
    )


@router.patch("/axioms/{id}/description", response_model=AxiomOut)
def update_axiom_description(
    id: int, body: DescriptionUpdate, dem: DemServices = Depends(dem_services)
) -> AxiomOut:
    return dem.axioms.set_description(id, body.description)


@router.post("/axioms/{id}/tags", response_model=AxiomOut)
def add_axiom_tag(id: int, body: TagAttach, dem: DemServices = Depends(dem_services)) -> AxiomOut:
    dem.tags.attach("axiom", id, body.tag_id)
    return dem.axioms.get(id)


@router.delete("/axioms/{id}/tags/{tag_id}", response_model=AxiomOut)
def remove_axiom_tag(
    id: int, tag_id: int, dem: DemServices = Depends(dem_services)
) -> AxiomOut:
    dem.tags.detach("axiom", id, tag_id)
    return dem.axioms.get(id)


@router.get("/axioms/by-name/{name}", response_model=AxiomOut)
def get_axiom_by_name(name: str, dem: DemServices = Depends(dem_services)) -> AxiomOut:
    return dem.axioms.get_by_name(name)


@router.get("/axioms/{ref}", response_model=AxiomOut)
def get_axiom(ref: str, dem: DemServices = Depends(dem_services)) -> AxiomOut:
    return dem.axioms.get(int(ref)) if ref.isdigit() else dem.axioms.get_by_public_id(ref)


@router.get("/axioms/public/{public_id}", response_model=AxiomOut)
def get_axiom_by_public_id(
    public_id: str, dem: DemServices = Depends(dem_services)
) -> AxiomOut:
    return dem.axioms.get_by_public_id(public_id)


@router.get("/axioms/{id}/used-in-theorems", response_model=list[TheoremOut])
def list_axiom_used_in_theorems(
    id: int, dem: DemServices = Depends(dem_services)
) -> list[TheoremOut]:
    return dem.axioms.list_used_in_theorems(id)


@router.get("/axiom-systems", response_model=list[AxiomSystemOut])
def list_axiom_systems(dem: DemServices = Depends(dem_services)) -> list[AxiomSystemOut]:
    return dem.axioms.list_systems()


@router.post(
    "/axiom-systems", response_model=AxiomSystemOut, status_code=status.HTTP_201_CREATED
)
def register_axiom_system(
    body: AxiomSystemCreate, dem: DemServices = Depends(dem_services)
) -> AxiomSystemOut:
    return dem.axioms.register_system(name=body.name, remarks=body.remarks)


@router.get("/axiom-systems/{id}", response_model=AxiomSystemOut)
def get_axiom_system(id: int, dem: DemServices = Depends(dem_services)) -> AxiomSystemOut:
    return dem.axioms.get_system(id)


@router.get("/axiom-systems/{id}/members", response_model=list[AxiomOut])
def list_axiom_system_members(id: int, dem: DemServices = Depends(dem_services)) -> list[AxiomOut]:
    return dem.axioms.list_system_members(id)


@router.post("/axiom-systems/{id}/members", status_code=status.HTTP_204_NO_CONTENT)
def add_axiom_system_member(
    id: int, body: AxiomSystemMemberAdd, dem: DemServices = Depends(dem_services)
) -> None:
    dem.axioms.add_to_system(id, body.axiom_id)


@router.delete(
    "/axiom-systems/{id}/members/{axiom_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_axiom_system_member(
    id: int, axiom_id: int, dem: DemServices = Depends(dem_services)
) -> None:
    dem.axioms.remove_from_system(id, axiom_id)


@router.get(
    "/axiom-systems/{child_id}/is-subset-of/{parent_id}", response_model=IsSubsetOut
)
def is_axiom_system_subset(
    child_id: int, parent_id: int, dem: DemServices = Depends(dem_services)
) -> IsSubsetOut:
    return IsSubsetOut(is_subset=dem.axioms.is_subset(child_id, parent_id))


@router.get("/axiom-systems/{id}/theorems", response_model=list[TheoremOut])
def list_axiom_system_theorems(
    id: int, dem: DemServices = Depends(dem_services)
) -> list[TheoremOut]:
    return dem.axioms.list_theorems_provable_in_system(id)
