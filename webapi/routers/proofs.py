from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select

from dem.api import DemServices
from dem.db.models.inference import Axiom
from dem.db.models.theorem import (
    Proof,
    ProofStep,
    ProofStepArg,
    ProofStepSubstProp,
    ProofStepSubstPropParam,
    ProofStepSubstTerm,
)
from dem.errors import ProofValidationError, ValidationError
from dem.types import (
    AssumptionStepInput,
    AxiomStepInput,
    GenStepInput,
    ImplicationIntroStepInput,
    MPStepInput,
    PremiseStepInput,
    ProofStepInput,
    PropSubst,
    Substitution,
    Token,
    TermSubst,
    TheoremStepInput,
)
from webapi.deps import dem_services
from webapi.routers.formulas import formula_details
from webapi.schemas import (
    AxiomOut,
    BackwardStepSuggestOut,
    BackwardStepSuggestRequest,
    BackwardStepSuggestionOut,
    ComputeGenTokensRequest,
    ComputeSubstitutedTokensRequest,
    DirectDependenciesOut,
    FormulaDetailOut,
    FormulaOut,
    InferenceRuleOut,
    IsSubsetOut,
    LemmaDependencyOut,
    ProofCreate,
    ProofOut,
    ProofStateOut,
    ProofStepCreate,
    ProofStepFollowupOut,
    ProofStepOut,
    PropSubstOut,
    SubstitutionIn,
    StepSuggestOut,
    StepSuggestRequest,
    SubstitutionOut,
    TermSubstOut,
    TokenOut,
    TheoremOut,
    ValidateResultOut,
)

router = APIRouter(tags=["proofs"])


def _to_substitution(subst: SubstitutionIn) -> Substitution:
    return Substitution(
        prop_substs=tuple(
            PropSubst(
                source_symbol_id=item.source_symbol_id,
                body_formula_id=item.body_formula_id,
                formal_param_symbol_ids=tuple(item.formal_param_symbol_ids),
            )
            for item in subst.prop_substs
        ),
        term_substs=tuple(
            TermSubst(
                source_symbol_id=item.source_symbol_id, target_formula_id=item.target_formula_id
            )
            for item in subst.term_substs
        ),
    )


def _token_payload(tokens):
    return [
        {"symbol_id": token.symbol_id, "de_bruijn_index": token.de_bruijn_index}
        for token in tokens
    ]


def _subst_out(subst: Substitution) -> SubstitutionOut:
    return SubstitutionOut(
        prop_substs=[
            PropSubstOut(
                source_symbol_id=item.source_symbol_id,
                body_formula_id=item.body_formula_id,
                formal_param_symbol_ids=list(item.formal_param_symbol_ids),
            )
            for item in subst.prop_substs
        ],
        term_substs=[
            TermSubstOut(
                source_symbol_id=item.source_symbol_id,
                target_formula_id=item.target_formula_id,
            )
            for item in subst.term_substs
        ],
    )


def _to_step_input(body: ProofStepCreate) -> ProofStepInput:
    if body.kind == "premise":
        if body.premise_ord is None:
            raise ValidationError("premise step requires premise_ord")
        return PremiseStepInput(premise_ord=body.premise_ord)
    if body.kind == "axiom":
        if body.axiom_id is None:
            raise ValidationError("axiom step requires axiom_id")
        return AxiomStepInput(axiom_id=body.axiom_id, subst=_to_substitution(body.subst))
    if body.kind == "theorem":
        if body.applied_proof_id is None:
            raise ValidationError("theorem step requires applied_proof_id")
        return TheoremStepInput(
            applied_proof_id=body.applied_proof_id,
            subst=_to_substitution(body.subst),
            arg_step_ords=tuple(body.arg_step_ords),
        )
    if body.kind == "mp":
        if body.antecedent_step_ord is None or body.implication_step_ord is None:
            raise ValidationError(
                "mp step requires antecedent_step_ord and implication_step_ord"
            )
        return MPStepInput(
            antecedent_step_ord=body.antecedent_step_ord,
            implication_step_ord=body.implication_step_ord,
        )
    if body.kind == "gen":
        if body.body_step_ord is None or body.gen_variable_symbol_id is None:
            raise ValidationError(
                "gen step requires body_step_ord and gen_variable_symbol_id"
            )
        return GenStepInput(
            body_step_ord=body.body_step_ord,
            gen_variable_symbol_id=body.gen_variable_symbol_id,
        )
    if body.kind == "assumption":
        return AssumptionStepInput()
    if body.kind == "imp_intro":
        if body.assumption_step_ord is None or body.body_step_ord is None:
            raise ValidationError(
                "imp_intro step requires assumption_step_ord and body_step_ord"
            )
        return ImplicationIntroStepInput(
            assumption_step_ord=body.assumption_step_ord,
            body_step_ord=body.body_step_ord,
        )
    raise ValidationError(f"unknown step kind: {body.kind}")


def _step_detail(dem: DemServices, step: ProofStep) -> ProofStepOut:
    # ProofService has no accessor for proof_step_arg / proof_step_subst_* rows
    # (they're internal to validate()'s preload), so they're read directly here
    # for display purposes only; dem/ itself is not modified.
    arg_step_ords = list(
        dem.session.scalars(
            select(ProofStepArg.referenced_step_ord)
            .where(ProofStepArg.proof_id == step.proof_id, ProofStepArg.step_ord == step.ord)
            .order_by(ProofStepArg.arg_ord)
        )
    )
    term_rows = dem.session.scalars(
        select(ProofStepSubstTerm).where(
            ProofStepSubstTerm.proof_id == step.proof_id,
            ProofStepSubstTerm.step_ord == step.ord,
        ).order_by(ProofStepSubstTerm.source_symbol_id)
    ).all()
    term_substs = [
        TermSubstOut(source_symbol_id=row.source_symbol_id, target_formula_id=row.target_formula_id)
        for row in term_rows
    ]

    prop_rows = dem.session.scalars(
        select(ProofStepSubstProp).where(
            ProofStepSubstProp.proof_id == step.proof_id,
            ProofStepSubstProp.step_ord == step.ord,
        ).order_by(ProofStepSubstProp.source_symbol_id)
    ).all()
    prop_substs = []
    for row in prop_rows:
        params = list(
            dem.session.scalars(
                select(ProofStepSubstPropParam.formal_param_symbol_id)
                .where(
                    ProofStepSubstPropParam.proof_id == step.proof_id,
                    ProofStepSubstPropParam.step_ord == step.ord,
                    ProofStepSubstPropParam.source_symbol_id == row.source_symbol_id,
                )
                .order_by(ProofStepSubstPropParam.ord)
            )
        )
        prop_substs.append(
            PropSubstOut(
                source_symbol_id=row.source_symbol_id,
                body_formula_id=row.body_formula_id,
                formal_param_symbol_ids=params,
            )
        )

    return _step_out(step, arg_step_ords, term_substs, prop_substs)


def _step_out(
    step: ProofStep,
    arg_step_ords: list[int],
    term_substs: list[TermSubstOut],
    prop_substs: list[PropSubstOut],
) -> ProofStepOut:
    return ProofStepOut(
        proof_id=step.proof_id,
        ord=step.ord,
        step_kind=step.step_kind,
        conclusion_formula=FormulaOut.model_validate(step.conclusion_formula, from_attributes=True),
        premise_ord=step.premise_ord,
        axiom=AxiomOut.model_validate(step.axiom, from_attributes=True) if step.axiom is not None else None,
        applied_proof_id=step.applied_proof_id,
        inference_rule=(
            InferenceRuleOut.model_validate(step.inference_rule, from_attributes=True)
            if step.inference_rule is not None
            else None
        ),
        gen_variable_symbol_id=step.gen_variable_symbol_id,
        arg_step_ords=arg_step_ords,
        term_substs=term_substs,
        prop_substs=prop_substs,
        remarks=step.remarks,
        created_at=step.created_at,
    )


@router.post("/proofs/{id}/steps/suggest", response_model=StepSuggestOut)
def suggest_proof_step(
    id: int, body: StepSuggestRequest, dem: DemServices = Depends(dem_services)
) -> StepSuggestOut:
    result = dem.proofs.suggest_step(
        id,
        kind=body.kind,
        applied_theorem_id=body.applied_theorem_id,
        axiom_id=body.axiom_id,
        arg_step_ords=body.arg_step_ords,
        goal_tokens=(
            [token.to_domain() for token in body.goal_tokens]
            if body.goal_tokens is not None
            else None
        ),
    )
    subst = result["subst"]
    return StepSuggestOut(
        applied_proof_id=result["applied_proof_id"],
        subst=SubstitutionOut(
            prop_substs=[
                PropSubstOut(
                    source_symbol_id=item.source_symbol_id,
                    body_formula_id=item.body_formula_id,
                    formal_param_symbol_ids=list(item.formal_param_symbol_ids),
                )
                for item in subst.prop_substs
            ],
            term_substs=[
                TermSubstOut(
                    source_symbol_id=item.source_symbol_id,
                    target_formula_id=item.target_formula_id,
                )
                for item in subst.term_substs
            ],
        ),
        undetermined=result["undetermined"],
        defaulted_to_identity=result["defaulted_to_identity"],
        conclusion_tokens=[
            {"symbol_id": token.symbol_id, "de_bruijn_index": token.de_bruijn_index}
            for token in result["conclusion_tokens"]
        ],
        premise_count=result["premise_count"],
        arg_candidates=result["arg_candidates"],
    )


@router.post(
    "/proofs/{id}/steps/suggest-backward",
    response_model=BackwardStepSuggestOut,
)
def suggest_proof_step_backward(
    id: int,
    body: BackwardStepSuggestRequest,
    dem: DemServices = Depends(dem_services),
) -> BackwardStepSuggestOut:
    """Suggest an axiom/theorem application followed by at most three MPs."""
    suggestions = dem.proofs.suggest_backward_steps(
        id,
        kind=body.kind,
        applied_theorem_id=body.applied_theorem_id,
        axiom_id=body.axiom_id,
        goal_tokens=[token.to_domain() for token in body.goal_tokens],
        subst=_to_substitution(body.subst),
    )
    return BackwardStepSuggestOut(
        candidates=[
            BackwardStepSuggestionOut(
                match_depth=item.match_depth,
                applied_proof_id=item.applied_proof_id,
                subst=_subst_out(item.subst),
                undetermined=item.undetermined,
                defaulted_to_identity=item.defaulted_to_identity,
                application_conclusion_tokens=_token_payload(
                    item.application_conclusion_tokens
                ),
                antecedent_goals=[
                    _token_payload(tokens) for tokens in item.antecedent_goals
                ],
                intermediate_conclusions=[
                    _token_payload(tokens)
                    for tokens in item.intermediate_conclusions
                ],
                premise_count=item.premise_count,
                premise_goals=[
                    _token_payload(tokens) for tokens in item.premise_goals
                ],
                arg_candidates=item.arg_candidates,
            )
            for item in suggestions
        ]
    )


@router.get("/inference-rules", response_model=list[InferenceRuleOut])
def list_inference_rules(dem: DemServices = Depends(dem_services)) -> list[InferenceRuleOut]:
    return dem.proofs.list_inference_rules()


@router.post("/proofs", response_model=ProofOut, status_code=status.HTTP_201_CREATED)
def create_proof(body: ProofCreate, dem: DemServices = Depends(dem_services)) -> ProofOut:
    return dem.proofs.create_proof(theorem_id=body.theorem_id, name=body.name, remarks=body.remarks)


@router.get("/proofs/{ref}", response_model=ProofOut)
def get_proof(ref: str, dem: DemServices = Depends(dem_services)) -> ProofOut:
    return dem.proofs.get(int(ref)) if ref.isdigit() else dem.proofs.get_by_public_id(ref)


@router.get("/proofs/public/{public_id}", response_model=ProofOut)
def get_proof_by_public_id(
    public_id: str, dem: DemServices = Depends(dem_services)
) -> ProofOut:
    return dem.proofs.get_by_public_id(public_id)


@router.get("/proofs/{id}/state", response_model=ProofStateOut)
def get_proof_state(
    id: int, dem: DemServices = Depends(dem_services)
) -> ProofStateOut:
    return ProofStateOut.model_validate(
        dem.proofs.get_state(id), from_attributes=True
    )


@router.get("/theorems/{id}/proofs", response_model=list[ProofOut])
def list_proofs_for_theorem(id: int, dem: DemServices = Depends(dem_services)) -> list[ProofOut]:
    return dem.proofs.list_for_theorem(id)


@router.post(
    "/proofs/{id}/steps", response_model=ProofStepOut, status_code=status.HTTP_201_CREATED
)
def add_proof_step(
    id: int, body: ProofStepCreate, dem: DemServices = Depends(dem_services)
) -> ProofStepOut:
    step_input = _to_step_input(body)
    step = dem.proofs.add_step(id, step_input, body.conclusion_formula_id)
    return _step_detail(dem, step)


@router.get("/proofs/{id}/steps", response_model=list[ProofStepOut])
def list_proof_steps(id: int, dem: DemServices = Depends(dem_services)) -> list[ProofStepOut]:
    steps = dem.proofs.list_steps(id)
    if not steps:
        return []

    # Read each child table once, regardless of step/substitution count.
    args: dict[int, list[int]] = {}
    for row in dem.session.scalars(
        select(ProofStepArg)
        .where(ProofStepArg.proof_id == id)
        .order_by(ProofStepArg.step_ord, ProofStepArg.arg_ord)
    ):
        args.setdefault(row.step_ord, []).append(row.referenced_step_ord)

    terms: dict[int, list[TermSubstOut]] = {}
    for row in dem.session.scalars(
        select(ProofStepSubstTerm)
        .where(ProofStepSubstTerm.proof_id == id)
        .order_by(ProofStepSubstTerm.step_ord, ProofStepSubstTerm.source_symbol_id)
    ):
        terms.setdefault(row.step_ord, []).append(
            TermSubstOut(
                source_symbol_id=row.source_symbol_id,
                target_formula_id=row.target_formula_id,
            )
        )

    params: dict[tuple[int, int], list[int]] = {}
    for row in dem.session.scalars(
        select(ProofStepSubstPropParam)
        .where(ProofStepSubstPropParam.proof_id == id)
        .order_by(
            ProofStepSubstPropParam.step_ord,
            ProofStepSubstPropParam.source_symbol_id,
            ProofStepSubstPropParam.ord,
        )
    ):
        params.setdefault((row.step_ord, row.source_symbol_id), []).append(
            row.formal_param_symbol_id
        )

    props: dict[int, list[PropSubstOut]] = {}
    for row in dem.session.scalars(
        select(ProofStepSubstProp)
        .where(ProofStepSubstProp.proof_id == id)
        .order_by(ProofStepSubstProp.step_ord, ProofStepSubstProp.source_symbol_id)
    ):
        props.setdefault(row.step_ord, []).append(
            PropSubstOut(
                source_symbol_id=row.source_symbol_id,
                body_formula_id=row.body_formula_id,
                formal_param_symbol_ids=params.get((row.step_ord, row.source_symbol_id), []),
            )
        )

    return [
        _step_out(step, args.get(step.ord, []), terms.get(step.ord, []), props.get(step.ord, []))
        for step in steps
    ]


@router.get(
    "/proofs/{id}/steps/{ord}/followups",
    response_model=list[ProofStepFollowupOut],
)
def list_proof_step_followups(
    id: int, ord: int, dem: DemServices = Depends(dem_services)
) -> list[ProofStepFollowupOut]:
    return [
        ProofStepFollowupOut.model_validate(item, from_attributes=True)
        for item in dem.proofs.list_step_followups(id, ord, max_depth=1)
    ]


@router.get("/proofs/{id}/formulas", response_model=list[FormulaDetailOut])
def list_proof_formulas(
    id: int, dem: DemServices = Depends(dem_services)
) -> list[FormulaDetailOut]:
    """Every distinct conclusion formula of this proof, with its tokens.

    `ProofStepOut.conclusion_formula` is the lightweight `FormulaOut`, so a view
    that renders the formulas has to fetch the tokens itself. Doing that one id
    at a time costs one request per distinct formula. This is the same data in
    one response.

    Deduplicated: proofs reuse a conclusion formula across steps.
    """
    dem.proofs.get(id)  # 404 before returning an empty list for an unknown proof
    formula_ids = (
        select(ProofStep.conclusion_formula_id)
        .where(ProofStep.proof_id == id)
        .distinct()
        .scalar_subquery()
    )
    return formula_details(dem.session, formula_ids)


@router.get("/proofs/{id}/direct-dependencies", response_model=DirectDependenciesOut)
def list_direct_dependencies(
    id: int, dem: DemServices = Depends(dem_services)
) -> DirectDependenciesOut:
    """The axioms and lemma theorems this proof's steps cite directly.

    The dependency tree on the theorem page needs a name and status per direct
    lemma. Reading them from the steps costs one `GET /proofs/{id}` per applied
    proof and one `GET /theorems/{id}` per lemma -- a few hundred requests for
    the large proofs. This is the same one-hop answer in one response.

    Both lists keep the order of first citation. Lemmas are deduplicated by
    theorem; if one theorem is cited through two proofs, the first cited wins.
    """
    dem.proofs.get(id)  # 404 before returning empty lists for an unknown proof
    axiom_ids: dict[int, None] = {}
    applied_proof_ids: dict[int, None] = {}
    for step_kind, axiom_id, applied_proof_id in dem.session.execute(
        select(ProofStep.step_kind, ProofStep.axiom_id, ProofStep.applied_proof_id)
        .where(ProofStep.proof_id == id, ProofStep.step_kind.in_(("axiom", "theorem")))
        .order_by(ProofStep.ord)
    ):
        if step_kind == "axiom":
            axiom_ids.setdefault(axiom_id)
        else:
            applied_proof_ids.setdefault(applied_proof_id)

    axioms = {
        axiom.id: axiom
        for axiom in dem.session.scalars(select(Axiom).where(Axiom.id.in_(axiom_ids)))
    }
    # Proof.theorem is lazy="joined", so the lemma theorems come in the same query.
    proofs = {
        proof.id: proof
        for proof in dem.session.scalars(select(Proof).where(Proof.id.in_(applied_proof_ids)))
    }

    lemmas: list[LemmaDependencyOut] = []
    seen_theorem_ids: set[int] = set()
    for proof_id in applied_proof_ids:
        proof = proofs[proof_id]
        if proof.theorem_id in seen_theorem_ids:
            continue
        seen_theorem_ids.add(proof.theorem_id)
        lemmas.append(
            LemmaDependencyOut(
                proof_id=proof.id,
                theorem=TheoremOut.model_validate(proof.theorem, from_attributes=True),
            )
        )
    return DirectDependenciesOut(
        axioms=[
            AxiomOut.model_validate(axioms[axiom_id], from_attributes=True)
            for axiom_id in axiom_ids
        ],
        lemmas=lemmas,
        applied_proofs={proof_id: proofs[proof_id].theorem_id for proof_id in applied_proof_ids},
    )


@router.post("/proofs/{id}/validate", response_model=ValidateResultOut)
def validate_proof(id: int, dem: DemServices = Depends(dem_services)) -> ValidateResultOut:
    # ProofService.validate() intentionally persists status='rejected' as a
    # side effect of raising ProofValidationError (see docs/design/api/proof-service.md).
    # The webapi request-scoped transaction (dem_services()) rolls back on any
    # exception propagating out of the route, which would silently discard
    # that persisted 'rejected' status. Commit explicitly before re-raising so
    # the rejection is durable and visible to a subsequent GET /proofs/{id}.
    try:
        dem.proofs.validate(id)
    except ProofValidationError:
        dem.session.commit()
        raise
    return ValidateResultOut(status=dem.proofs.get(id).status)


@router.get("/proofs/{id}/used-axioms", response_model=list[AxiomOut])
def list_used_axioms(id: int, dem: DemServices = Depends(dem_services)) -> list[AxiomOut]:
    return dem.proofs.list_used_axioms(id)


@router.get("/proofs/{id}/is-valid-in-system/{axiom_system_id}", response_model=IsSubsetOut)
def is_proof_valid_in_system(
    id: int, axiom_system_id: int, dem: DemServices = Depends(dem_services)
) -> IsSubsetOut:
    return IsSubsetOut(is_subset=dem.proofs.is_valid_in_system(id, axiom_system_id))


@router.post("/proofs/compute-substituted-tokens", response_model=list[TokenOut])
def compute_substituted_tokens(
    body: ComputeSubstitutedTokensRequest, dem: DemServices = Depends(dem_services)
) -> list[TokenOut]:
    tokens = dem.proofs.compute_substituted_tokens(body.formula_id, _to_substitution(body.subst))
    return [
        TokenOut(position=i, symbol_id=t.symbol_id, de_bruijn_index=t.de_bruijn_index)
        for i, t in enumerate(tokens)
    ]


@router.post("/proofs/compute-gen-tokens", response_model=list[TokenOut])
def compute_gen_tokens(
    body: ComputeGenTokensRequest, dem: DemServices = Depends(dem_services)
) -> list[TokenOut]:
    tokens = dem.proofs.compute_gen_tokens(body.body_formula_id, body.gen_variable_symbol_id)
    return [
        TokenOut(position=i, symbol_id=t.symbol_id, de_bruijn_index=t.de_bruijn_index)
        for i, t in enumerate(tokens)
    ]
