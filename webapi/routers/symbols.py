from __future__ import annotations

from fastapi import APIRouter, Depends, status
from dem.api import DemServices
from webapi.deps import dem_services
from webapi.schemas import (
    FormulaTypeOut,
    SymbolAliasCreate,
    SymbolAliasOut,
    SymbolCreate,
    SymbolLatexTemplateUpdate,
    SymbolNotationUpdate,
    SymbolOut,
    SymbolWithUsageOut,
    SymbolRoleAssign,
    SymbolTypeOut,
)

router = APIRouter(tags=["symbols"])


@router.get("/formula-types", response_model=list[FormulaTypeOut])
def list_formula_types(dem: DemServices = Depends(dem_services)) -> list[FormulaTypeOut]:
    return dem.symbols.list_formula_types()


@router.get("/symbol-types", response_model=list[SymbolTypeOut])
def list_symbol_types(dem: DemServices = Depends(dem_services)) -> list[SymbolTypeOut]:
    return dem.symbols.list_symbol_types()


@router.get("/symbols", response_model=list[SymbolWithUsageOut])
def list_symbols(
    symbol_type_id: int | None = None,
    with_usage: bool = False,
    dem: DemServices = Depends(dem_services),
) -> list[SymbolWithUsageOut]:
    if with_usage:
        rows = dem.symbols.list_with_usage(symbol_type_id)
    else:
        symbols = (
            dem.symbols.list_by_type(symbol_type_id)
            if symbol_type_id is not None
            else dem.symbols.list_all()
        )
        rows = [(symbol, None) for symbol in symbols]
    return [
        SymbolWithUsageOut(
            **SymbolOut.model_validate(symbol, from_attributes=True).model_dump(),
            usage_count=usage_count,
        )
        for symbol, usage_count in rows
    ]


@router.get("/symbol-aliases", response_model=list[SymbolAliasOut])
def list_symbol_aliases(dem: DemServices = Depends(dem_services)) -> list[SymbolAliasOut]:
    return dem.symbols.list_aliases()


@router.post(
    "/symbols/{id}/aliases", response_model=SymbolAliasOut, status_code=status.HTTP_201_CREATED
)
def add_symbol_alias(
    id: int, body: SymbolAliasCreate, dem: DemServices = Depends(dem_services)
) -> SymbolAliasOut:
    return dem.symbols.add_alias(id, body.alias)


@router.post("/symbols", response_model=SymbolOut, status_code=status.HTTP_201_CREATED)
def register_symbol(body: SymbolCreate, dem: DemServices = Depends(dem_services)) -> SymbolOut:
    return dem.symbols.register(
        name=body.name,
        symbol_type_id=body.symbol_type_id,
        arity=body.arity,
        is_primitive=body.is_primitive,
        notation_kind=body.notation_kind,
        precedence=body.precedence,
        latex_template=body.latex_template,
        remarks=body.remarks,
    )


@router.patch("/symbols/{id}/notation", response_model=SymbolOut)
def update_symbol_notation(
    id: int, body: SymbolNotationUpdate, dem: DemServices = Depends(dem_services)
) -> SymbolOut:
    return dem.symbols.set_notation(id, body.notation_kind, body.precedence)


@router.patch("/symbols/{id}/latex-template", response_model=SymbolOut)
def update_symbol_latex_template(
    id: int, body: SymbolLatexTemplateUpdate, dem: DemServices = Depends(dem_services)
) -> SymbolOut:
    return dem.symbols.set_latex_template(id, body.latex_template)


@router.get("/symbols/by-name/{name}", response_model=SymbolOut)
def get_symbol_by_name(name: str, dem: DemServices = Depends(dem_services)) -> SymbolOut:
    return dem.symbols.get_by_name(name)


@router.get("/symbols/{ref}", response_model=SymbolOut)
def get_symbol(ref: str, dem: DemServices = Depends(dem_services)) -> SymbolOut:
    return dem.symbols.get(int(ref)) if ref.isdigit() else dem.symbols.get_by_public_id(ref)


@router.get("/symbols/public/{public_id}", response_model=SymbolOut)
def get_symbol_by_public_id(
    public_id: str, dem: DemServices = Depends(dem_services)
) -> SymbolOut:
    return dem.symbols.get_by_public_id(public_id)


@router.get("/symbol-roles/{role}", response_model=SymbolOut)
def get_symbol_by_role(role: str, dem: DemServices = Depends(dem_services)) -> SymbolOut:
    return dem.symbols.get_by_role(role)


@router.post("/symbol-roles", status_code=status.HTTP_204_NO_CONTENT)
def assign_symbol_role(body: SymbolRoleAssign, dem: DemServices = Depends(dem_services)) -> None:
    dem.symbols.assign_role(body.role, body.symbol_id)
