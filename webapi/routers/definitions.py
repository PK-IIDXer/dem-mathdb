from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from dem.api import DemServices
from dem.db.models.definition import Definition
from dem.errors import ValidationError
from dem.types import (
    DefinitionInput,
    FunctionDefinitionInput,
    LogicalDefinitionInput,
    PredicateDefinitionInput,
    QuantPropDefinitionInput,
    QuantTermDefinitionInput,
)
from webapi.deps import dem_services
from webapi.pagination import Cursor, Limit, named_query, read_page
from webapi.schemas import (
    AxiomOut,
    DefinitionCreate,
    DefinitionOut,
    DescriptionUpdate,
    SymbolOut,
    TagAttach,
)

router = APIRouter(tags=["definitions"])


def _to_definition_input(body: DefinitionCreate) -> DefinitionInput:
    if body.kind == "predicate":
        return PredicateDefinitionInput(
            name=body.name,
            param_symbol_ids=tuple(body.param_symbol_ids),
            body_formula_id=body.body_formula_id,
            requires_existence_proof=body.requires_existence_proof,
            requires_uniqueness_proof=body.requires_uniqueness_proof,
            remarks=body.remarks,
            latex_template=body.latex_template,
        )
    if body.kind == "logical":
        return LogicalDefinitionInput(
            name=body.name,
            param_symbol_ids=tuple(body.param_symbol_ids),
            body_formula_id=body.body_formula_id,
            remarks=body.remarks,
            latex_template=body.latex_template,
        )
    if body.kind == "function":
        return FunctionDefinitionInput(
            name=body.name,
            param_symbol_ids=tuple(body.param_symbol_ids),
            body_formula_id=body.body_formula_id,
            remarks=body.remarks,
            latex_template=body.latex_template,
        )
    if body.kind == "quant_prop":
        if len(body.param_symbol_ids) != 1:
            raise ValidationError("quant_prop definition requires exactly one param_symbol_id")
        return QuantPropDefinitionInput(
            name=body.name,
            param_symbol_id=body.param_symbol_ids[0],
            body_formula_id=body.body_formula_id,
            remarks=body.remarks,
            latex_template=body.latex_template,
        )
    if body.kind == "quant_term":
        if len(body.param_symbol_ids) != 1:
            raise ValidationError("quant_term definition requires exactly one param_symbol_id")
        return QuantTermDefinitionInput(
            name=body.name,
            param_symbol_id=body.param_symbol_ids[0],
            body_formula_id=body.body_formula_id,
            remarks=body.remarks,
            latex_template=body.latex_template,
        )
    raise ValidationError(f"unknown definition kind: {body.kind}")


@router.get("/definitions", response_model=list[DefinitionOut])
def list_definitions(
    response: Response,
    search: str | None = None,
    tag_id: list[int] | None = Query(default=None),
    exclude_tag_id: list[int] | None = Query(default=None),
    dem: DemServices = Depends(dem_services),
    limit: Limit = None,
    cursor: Cursor = None,
) -> list[DefinitionOut]:
    if limit is None and cursor is None and not exclude_tag_id:
        return dem.definitions.list_all(search=search, tag_ids=tag_id)
    return read_page(
        dem.session,
        Definition,
        named_query(Definition, search, tag_id, exclude_tag_id),
        response,
        limit,
        cursor,
    )


@router.post("/definitions", response_model=DefinitionOut, status_code=status.HTTP_201_CREATED)
def register_definition(
    body: DefinitionCreate, dem: DemServices = Depends(dem_services)
) -> DefinitionOut:
    definition_input = _to_definition_input(body)
    return dem.definitions.register(definition_input)


@router.patch("/definitions/{id}/description", response_model=DefinitionOut)
def update_definition_description(
    id: int, body: DescriptionUpdate, dem: DemServices = Depends(dem_services)
) -> DefinitionOut:
    return dem.definitions.set_description(id, body.description)


@router.post("/definitions/{id}/tags", response_model=DefinitionOut)
def add_definition_tag(
    id: int, body: TagAttach, dem: DemServices = Depends(dem_services)
) -> DefinitionOut:
    dem.tags.attach("definition", id, body.tag_id)
    return dem.definitions.get(id)


@router.delete("/definitions/{id}/tags/{tag_id}", response_model=DefinitionOut)
def remove_definition_tag(
    id: int, tag_id: int, dem: DemServices = Depends(dem_services)
) -> DefinitionOut:
    dem.tags.detach("definition", id, tag_id)
    return dem.definitions.get(id)


@router.get("/definitions/by-name/{name}", response_model=DefinitionOut)
def get_definition_by_name(name: str, dem: DemServices = Depends(dem_services)) -> DefinitionOut:
    return dem.definitions.get_by_name(name)


@router.get("/definitions/{ref}", response_model=DefinitionOut)
def get_definition(ref: str, dem: DemServices = Depends(dem_services)) -> DefinitionOut:
    return (
        dem.definitions.get(int(ref))
        if ref.isdigit()
        else dem.definitions.get_by_public_id(ref)
    )


@router.get("/definitions/public/{public_id}", response_model=DefinitionOut)
def get_definition_by_public_id(
    public_id: str, dem: DemServices = Depends(dem_services)
) -> DefinitionOut:
    return dem.definitions.get_by_public_id(public_id)


@router.get("/definitions/{id}/symbol", response_model=SymbolOut)
def get_definition_symbol(id: int, dem: DemServices = Depends(dem_services)) -> SymbolOut:
    return dem.definitions.get_symbol(id)


@router.get("/definitions/{id}/axiom", response_model=AxiomOut)
def get_definition_axiom(id: int, dem: DemServices = Depends(dem_services)) -> AxiomOut:
    return dem.definitions.get_axiom(id)


@router.get("/definitions/{id}/formal-params", response_model=list[SymbolOut])
def list_definition_formal_params(
    id: int, dem: DemServices = Depends(dem_services)
) -> list[SymbolOut]:
    return dem.definitions.list_formal_params(id)
