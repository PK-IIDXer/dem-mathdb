"""Phase 0 authoring contracts on a small, independently seeded database."""
import ast
import asyncio
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from dem.api import DemServices
from dem.db.models import Base
from dem.db.models.theorem import ProofStep, ProofStepArg, ProofStepSubstTerm, ProofStepSubstProp, ProofStepSubstPropParam
from dem.db.seed import seed_language, seed_inference_rules
from dem.errors import ConflictError, FormulaValidationError, ProofValidationError
from dem.services.proof import ProofService
from dem.types import (AxiomStepInput, AssumptionStepInput, GenStepInput,
                       ImplicationIntroStepInput, MPStepInput, PremiseStepInput,
                       TheoremStepInput, SymbolTypeName, Token)
from webapi.errors import register_exception_handlers


@pytest.fixture
def dem():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_language(session)
        seed_inference_rules(session)
        yield DemServices(session)
    engine.dispose()


def prop(dem, name):
    kind = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value)
    symbol = dem.symbols.register(name, kind.id, 0)
    return dem.formulas.register([Token(symbol_id=symbol.id)])


def implication(dem, a, b):
    return dem.formulas.register([Token(symbol_id=dem.symbols.get_by_role("implication").id),
        *dem.proofs._tokens_for_formula(a.id), *dem.proofs._tokens_for_formula(b.id)])


def counts(dem):
    return [dem.session.scalar(select(func.count()).select_from(model)) for model in
            (ProofStep, ProofStepArg, ProofStepSubstTerm, ProofStepSubstProp, ProofStepSubstPropParam)]


def test_display_gate_registration_edits_and_slot_permutation(dem):
    kind = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_TERM_VAR.value)
    first = dem.symbols.register("display_a", kind.id, 0)
    with pytest.raises(ConflictError) as caught:
        dem.symbols.register("display_b", kind.id, 0, latex_template=" display_a ")
    assert caught.value.code == "symbol.display_collision"
    assert caught.value.details["symbol_id"] == first.id
    second = dem.symbols.register("display_b", kind.id, 0)
    with pytest.raises(ConflictError):
        dem.symbols.set_latex_template(second.id, "display_a")
    assert second.latex_template is None
    dem.symbols.set_latex_template(first.id, "display_a")  # exclude self
    function = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FUNCTION.value)
    dem.symbols.register("slot_a", function.id, 2, latex_template="#1 + #2")
    with pytest.raises(ConflictError):
        dem.symbols.register("slot_b", function.id, 2, latex_template="#2 + #1")
    dem.symbols.register("prefix_a", function.id, 2, latex_template="display_op")
    infix = dem.symbols.register("infix_a", function.id, 2, notation_kind="infix", precedence=50, latex_template="display_op")
    with pytest.raises(ConflictError):
        dem.symbols.set_notation(infix.id, "prefix", None)
    assert infix.notation_kind == "infix"


@pytest.mark.parametrize("kind", ["premise", "axiom", "theorem", "mp", "gen", "intro"])
def test_incorrect_conclusion_is_rejected_before_any_step_rows(dem, kind):
    a, b = prop(dem, "a"), prop(dem, "b")
    ab = implication(dem, a, b)
    theorem = dem.theorems.register("target", b.id, [a.id, ab.id])
    proof = dem.proofs.create_proof(theorem.id)
    if kind == "premise":
        step = PremiseStepInput(0)
    elif kind == "axiom":
        step = AxiomStepInput(dem.axioms.register("axiom", a.id).id)
    elif kind == "theorem":
        lemma = dem.theorems.register("lemma", a.id, [a.id])
        cited = dem.proofs.create_proof(lemma.id)
        dem.proofs.add_step(cited.id, PremiseStepInput(0), a.id)
        dem.proofs.validate(cited.id)
        dem.proofs.add_step(proof.id, PremiseStepInput(0), a.id)
        step = TheoremStepInput(cited.id, arg_step_ords=(0,))
    elif kind == "mp":
        dem.proofs.add_step(proof.id, PremiseStepInput(0), a.id)
        dem.proofs.add_step(proof.id, PremiseStepInput(1), ab.id)
        step = MPStepInput(0, 1)
    elif kind == "gen":
        dem.proofs.add_step(proof.id, PremiseStepInput(0), a.id)
        term = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_TERM_VAR.value)
        x = dem.symbols.register("gen_x", term.id, 0)
        step = GenStepInput(0, x.id)
    else:
        dem.proofs.add_step(proof.id, AssumptionStepInput(), a.id)
        step = ImplicationIntroStepInput(0, 0)
    wrong = a if kind == "mp" else b
    before = counts(dem)
    with pytest.raises(ProofValidationError) as caught:
        dem.proofs.add_step(proof.id, step, wrong.id)
    assert caught.value.code == "proof.step_conclusion_mismatch"
    assert caught.value.details["actual"] == dem.proofs._tokens_for_formula(wrong.id)
    assert "diff_path" in caught.value.details
    assert counts(dem) == before
    assert proof.status == "draft"


def test_nested_difference_and_mp_antecedent_details(dem):
    a, b = prop(dem, "a"), prop(dem, "b")
    aa, ab = implication(dem, a, a), implication(dem, a, b)
    proof = dem.proofs.create_proof(dem.theorems.register("target", b.id, [aa.id, b.id]).id)
    with pytest.raises(ProofValidationError) as caught:
        dem.proofs.add_step(proof.id, PremiseStepInput(0), ab.id)
    assert caught.value.details["diff_path"] == [1]
    dem.proofs.add_step(proof.id, PremiseStepInput(0), aa.id)
    dem.proofs.add_step(proof.id, PremiseStepInput(1), b.id)
    with pytest.raises(ProofValidationError) as caught:
        dem.proofs.add_step(proof.id, MPStepInput(1, 0), a.id)
    assert caught.value.code == "proof.mp_antecedent_mismatch"
    assert caught.value.details["expected"] == dem.proofs._tokens_for_formula(a.id)
    assert caught.value.details["actual"] == dem.proofs._tokens_for_formula(b.id)


def test_append_reuses_verified_prefix_across_service_instances(dem, monkeypatch):
    import dem.services.proof as module
    a = prop(dem, "a")
    proof = dem.proofs.create_proof(dem.theorems.register("target", a.id, [a.id]).id)
    calls = []
    original = module.validate_proof_step
    def observe(*args, **kwargs):
        calls.append(kwargs["step"].ord)
        return original(*args, **kwargs)
    monkeypatch.setattr(module, "validate_proof_step", observe)
    statements = []
    engine = dem.session.get_bind()
    def record_sql(*args):
        statements.append(args[2])
    event.listen(engine, "before_cursor_execute", record_sql)
    try:
        for i in range(100):
            ProofService(dem.session).add_step(proof.id, PremiseStepInput(0), a.id)
            if i == 49:
                first_half = len(statements)
        assert len(statements) - first_half <= first_half
    finally:
        event.remove(engine, "before_cursor_execute", record_sql)
    assert calls == list(range(100))
    proof_id, formula_id = proof.id, a.id
    dem.session.commit()
    calls.clear()
    # The next transaction replays the prefix once, then appends incrementally.
    for _ in range(100):
        dem.proofs.add_step(proof_id, PremiseStepInput(0), formula_id)
    assert calls == list(range(200))
    dem.proofs.validate(proof_id)
    assert proof.status == "verified"


def test_rollback_and_edited_prefix_do_not_reuse_stale_judgements(dem):
    a, b = prop(dem, "a"), prop(dem, "b")
    proof = dem.proofs.create_proof(dem.theorems.register("target", a.id, [a.id, b.id]).id)
    dem.session.commit()
    dem.proofs.add_step(proof.id, PremiseStepInput(0), a.id)
    dem.session.rollback()
    assert dem.proofs.list_steps(proof.id) == []
    dem.proofs.add_step(proof.id, PremiseStepInput(1), b.id)
    nested = dem.session.begin_nested()
    dem.proofs.add_step(proof.id, PremiseStepInput(0), a.id)
    nested.rollback()
    assert dem.proofs.add_step(proof.id, PremiseStepInput(1), b.id).ord == 1
    first = dem.proofs.list_steps(proof.id)[0]
    first.conclusion_formula_id = a.id  # invalid persisted prefix
    dem.session.flush()
    with pytest.raises(ProofValidationError) as caught:
        dem.proofs.add_step(proof.id, PremiseStepInput(0), a.id)
    assert caught.value.step_ord == 0
    assert len(dem.proofs.list_steps(proof.id)) == 2


def test_raw_prefix_is_verified_before_interactive_append(dem):
    a, b = prop(dem, "a"), prop(dem, "b")
    proof = dem.proofs.create_proof(dem.theorems.register("target", a.id, [a.id]).id)
    dem.proofs.add_raw_steps(proof.id, [(PremiseStepInput(0), b.id)])
    with pytest.raises(ProofValidationError) as caught:
        dem.proofs.add_step(proof.id, PremiseStepInput(0), a.id)
    assert caught.value.step_ord == 0
    assert len(dem.proofs.list_steps(proof.id)) == 1


@pytest.mark.parametrize("exception", [
    FormulaValidationError("bad formula", 2, code="formula.type_mismatch"),
    ProofValidationError("bad step", 3, code="proof.step_conclusion_mismatch",
        details={"expected": [Token(symbol_id=7)], "actual": [Token(de_bruijn_index=0)], "diff_path": [1]}),
])
def test_structured_error_response_preserves_legacy_fields(exception):
    app = FastAPI()
    register_exception_handlers(app)
    handler = app.exception_handlers[type(exception) if isinstance(exception, ProofValidationError)
                                      else FormulaValidationError.__bases__[0]]
    response = asyncio.run(handler(None, exception))
    body = json.loads(response.body)
    assert response.status_code == 422
    assert body["detail"] == str(exception)
    assert body["code"] == exception.code
    if isinstance(exception, ProofValidationError):
        assert body["step_ord"] == 3
        assert body["details"]["expected"]["tokens"] == [
            {"position": 0, "symbol_id": 7, "de_bruijn_index": None}]
        assert body["details"]["actual"]["tokens"][0]["de_bruijn_index"] == 0
    else:
        assert body["position"] == 2


def test_every_formula_and_proof_validation_raise_has_code():
    root = Path(__file__).resolve().parents[1]
    for relative in ("dem/services/formula.py", "dem/services/proof.py"):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                call = node.exc
                if isinstance(call.func, ast.Name) and call.func.id in {"FormulaValidationError", "ProofValidationError"}:
                    assert "code" in {kw.arg for kw in call.keywords}, (relative, node.lineno)


def test_theorem_argument_and_generalization_details(dem):
    a, b = prop(dem, "a"), prop(dem, "b")
    lemma = dem.theorems.register("lemma", a.id, [a.id])
    cited = dem.proofs.create_proof(lemma.id)
    dem.proofs.add_step(cited.id, PremiseStepInput(0), a.id)
    dem.proofs.validate(cited.id)
    proof = dem.proofs.create_proof(dem.theorems.register("target", b.id, [b.id]).id)
    dem.proofs.add_step(proof.id, PremiseStepInput(0), b.id)
    with pytest.raises(ProofValidationError) as caught:
        dem.proofs.add_step(proof.id, TheoremStepInput(cited.id, arg_step_ords=(0,)), a.id)
    assert caught.value.code == "proof.arg_mismatch"
    assert caught.value.details == {"arg_index": 0,
        "expected": dem.proofs._tokens_for_formula(a.id), "actual": dem.proofs._tokens_for_formula(b.id)}
    term = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_TERM_VAR.value)
    variable = dem.symbols.register("generalized_x", term.id, 0)
    predicate = dem.symbols.get_symbol_type_by_name(SymbolTypeName.PREDICATE.value)
    p = dem.symbols.register("predicate_p", predicate.id, 1)
    px = dem.formulas.register([Token(symbol_id=p.id), Token(symbol_id=variable.id)])
    universal = dem.formulas.register(dem.proofs.compute_gen_tokens(px.id, variable.id))
    for assumed in (False, True):
        theorem = dem.theorems.register(f"gen_{assumed}", universal.id, [px.id])
        proof = dem.proofs.create_proof(theorem.id)
        dem.proofs.add_step(proof.id, AssumptionStepInput() if assumed else PremiseStepInput(0), px.id)
        with pytest.raises(ProofValidationError) as caught:
            dem.proofs.add_step(proof.id, GenStepInput(0, variable.id), universal.id)
        assert caught.value.code == ("proof.gen_variable_in_assumption" if assumed else "proof.gen_variable_in_premise")
        assert caught.value.details["variable_symbol_id"] == variable.id
        if not assumed:
            assert caught.value.details["premise_ord"] == 0


def test_wrong_step_http_422_leaves_draft_usable(dem):
    from webapi.main import app
    from webapi.deps import dem_services
    a, b = prop(dem, "a"), prop(dem, "b")
    proof = dem.proofs.create_proof(dem.theorems.register("target", a.id, [a.id]).id)
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[dem_services] = lambda: dem
    async def post(formula_id):
        body = json.dumps({"kind": "premise", "premise_ord": 0, "conclusion_formula_id": formula_id}).encode()
        path = f"/proofs/{proof.id}/steps"
        scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1", "method": "POST", "scheme": "http", "path": path,
            "raw_path": path.encode(), "root_path": "", "query_string": b"",
            "headers": [(b"host", b"test"), (b"content-type", b"application/json")],
            "server": ("test", 80), "client": ("test", 1234)}
        messages = []
        sent = False
        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            await asyncio.Event().wait()
        async def send(message):
            messages.append(message)
        await asyncio.wait_for(app(scope, receive, send), 10)
        status = next(m["status"] for m in messages if m["type"] == "http.response.start")
        payload = json.loads(b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body"))
        return status, payload
    try:
        status, payload = asyncio.run(post(b.id))
        assert status == 422
        assert payload["code"] == "proof.step_conclusion_mismatch"
        assert payload["step_ord"] == 0
        assert payload["details"]["expected"]["tokens"][0]["symbol_id"] is not None
        assert dem.proofs.list_steps(proof.id) == []
        status, payload = asyncio.run(post(a.id))
        assert status == 201 and payload["ord"] == 0
        dem.proofs.validate(proof.id)
        assert proof.status == "verified"
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
