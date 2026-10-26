from __future__ import annotations

from fastapi import APIRouter, Depends, status

from dem.api import DemServices
from dem.services.exploration import ExplorationDependencies, ExplorationNote
from webapi.deps import dem_services, get_local_namespace_name
from webapi.schemas import (
    AxiomOut,
    ExplorationCreate,
    ExplorationDependenciesOut,
    ExplorationOut,
    ExplorationPromotionCreate,
    ExplorationPromotionOut,
    FormulaOut,
    ProofOut,
)
from webapi.theorem_output import theorem_output, theorem_outputs


router = APIRouter(tags=["explorations"])


def _note_out(dem: DemServices, note: ExplorationNote) -> ExplorationOut:
    return ExplorationOut(
        theorem=theorem_output(dem.session, note.theorem),
        proof=ProofOut.model_validate(note.proof, from_attributes=True),
        premises=[
            FormulaOut.model_validate(formula, from_attributes=True)
            for formula in note.premises
        ],
        step_count=note.step_count,
        updated_at=note.updated_at,
    )


def _dependencies_out(
    dem: DemServices, dependencies: ExplorationDependencies
) -> ExplorationDependenciesOut:
    return ExplorationDependenciesOut(
        axioms=[
            AxiomOut.model_validate(axiom, from_attributes=True)
            for axiom in dependencies.axioms
        ],
        theorems=theorem_outputs(dem.session, dependencies.theorems),
    )


@router.post(
    "/explorations",
    response_model=ExplorationOut,
    status_code=status.HTTP_201_CREATED,
)
def create_exploration(
    body: ExplorationCreate,
    dem: DemServices = Depends(dem_services, scope="function"),
    namespace: str = Depends(get_local_namespace_name, scope="function"),
) -> ExplorationOut:
    return _note_out(
        dem,
        dem.explorations.create(
            body.name, body.premise_formula_ids, namespace=namespace
        ),
    )


@router.get("/explorations", response_model=list[ExplorationOut])
def list_explorations(
    dem: DemServices = Depends(dem_services, scope="function"),
) -> list[ExplorationOut]:
    return [_note_out(dem, note) for note in dem.explorations.list_all()]


@router.get("/explorations/{ref}", response_model=ExplorationOut)
def get_exploration(
    ref: str, dem: DemServices = Depends(dem_services, scope="function")
) -> ExplorationOut:
    return _note_out(dem, dem.explorations.get(ref))


@router.get(
    "/explorations/{ref}/steps/{step_ord}/dependencies",
    response_model=ExplorationDependenciesOut,
)
def list_exploration_line_dependencies(
    ref: str, step_ord: int, dem: DemServices = Depends(dem_services, scope="function")
) -> ExplorationDependenciesOut:
    return _dependencies_out(
        dem, dem.explorations.list_line_dependencies(ref, step_ord)
    )


@router.post(
    "/explorations/{ref}/steps/{step_ord}/promote",
    response_model=ExplorationPromotionOut,
    status_code=status.HTTP_201_CREATED,
)
def promote_exploration_line(
    ref: str,
    step_ord: int,
    body: ExplorationPromotionCreate,
    dem: DemServices = Depends(dem_services, scope="function"),
    namespace: str = Depends(get_local_namespace_name, scope="function"),
) -> ExplorationPromotionOut:
    promoted = dem.explorations.promote(
        ref, step_ord, body.name, namespace=namespace
    )
    return ExplorationPromotionOut(
        theorem=theorem_output(dem.session, promoted.theorem),
        proof=ProofOut.model_validate(promoted.proof, from_attributes=True),
    )
