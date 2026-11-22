import copy
import json
from pathlib import Path

import pytest
from sqlalchemy import event, select

from dem.db.models import Package, PackageRelease, Symbol
from dem.db.seeds import seed_public_class_relations_layer
from dem.db.seeds.public_relation_definitions import DEFINITIONS, register_definitions

from dem.errors import FormulaValidationError, ProofValidationError, ValidationError
from dem.services.axiom import AxiomService
from dem.services.definition import DefinitionService
from dem.services.formula import FormulaService
from dem.services.package import check_release_dependencies, publish_release
from dem.services.proof import ProofService
from dem.services.theorem import TheoremService
from dem.types import AxiomStepInput, Substitution

SEED_PHASE = "public_class_relations"
SPEC = json.loads((Path(__file__).parent / "fixtures/public-relations-maps-spec.json").read_text(encoding="utf-8"))


def assert_definition(session, expected):
    ds, fs, ps = DefinitionService(session), FormulaService(session), ProofService(session)
    row = ds.get_by_name(expected["name"])
    axiom = ds.get_axiom(row.id)
    symbol = session.get(Symbol, row.new_symbol_id)
    assert (row.public_id, symbol.public_id, axiom.public_id, row.kind) == tuple(
        expected[key] for key in ("id", "symbol_id", "axiom_id", "kind")
    )
    assert (symbol.notation_kind, symbol.precedence, symbol.latex_template) == tuple(
        expected[key] for key in ("notation", "precedence", "latex")
    )
    tokens = ps._tokens_for_formula(axiom.formula_id)
    assert fs.get(axiom.formula_id).hash == expected["hash"]
    assert fs.print_text(tokens) == expected["dss"]
    assert fs.parse_text(expected["dss"])[0] == tokens


def test_definitions_and_notation(fresh_seeded_session):
    s = fresh_seeded_session
    for definition in SPEC["definitions"]:
        assert_definition(s, definition)
    formula = FormulaService(s)
    assert formula.parse_text("R ⊂ X × Y")[0] == formula.parse_text("R ⊂ (X × Y)")[0]
    for dss in ("a × b × c", "a ⊂ b ⊂ c"):
        with pytest.raises(FormulaValidationError):
            formula.parse_text(dss)


def test_statements_proof_dependencies_and_systems(fresh_seeded_session):
    s = fresh_seeded_session
    fs, ps, ts = FormulaService(s), ProofService(s), TheoremService(s)
    axs = AxiomService(s)
    systems = {name: axs.get_system_by_name(name).id for name in SPEC["systems"]}
    for expected in SPEC["theorems"]:
        theorem = ts.get_by_name(expected["name"])
        proof, = ps.list_for_theorem(theorem.id)
        assert (theorem.public_id, fs.get(theorem.conclusion_formula_id).hash) == (expected["id"], expected["hash"])
        tokens = fs.parse_text(expected["dss"])[0]
        assert tokens == ps._tokens_for_formula(theorem.conclusion_formula_id)
        assert fs.parse_text(fs.print_text(tokens))[0] == tokens
        assert [(form.hash, ps._tokens_for_formula(form.id)) for _, form in ts.list_premises(theorem.id)] == [
            (p["hash"], fs.parse_text(p["dss"])[0]) for p in expected["premises"]
        ]
        assert proof.status == "verified"
        assert len(ps.list_steps(proof.id)) == expected["steps"] <= 200
        assert [name for name, sid in systems.items() if ps.is_valid_in_system(proof.id, sid)] == expected["valid"]
        assert sorted(a.name for a in ps.list_used_axioms(proof.id)) == expected["axioms"]


def test_frozen_releases(fresh_seeded_session):
    s = fresh_seeded_session
    from test_public_zfc_mk import assert_ownership
    assert_ownership(s)
    actual = {}
    for release in s.scalars(select(PackageRelease).order_by(PackageRelease.id)):
        assert not check_release_dependencies(s, release.id)
        name = s.get(Package, release.package_id).name
        actual[f"{name}@{release.version}"] = publish_release(s, release.id).content_digest
    assert actual == SPEC["digests"]


def test_seed_all_returns_with_selects(fresh_seeded_session):
    s = fresh_seeded_session
    s.connection()
    statements = []

    def record(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement.lstrip().split()[0].upper())

    event.listen(s.get_bind(), "before_cursor_execute", record)
    try:
        # This phase ends with the class relations layer; seed_all also adds algebra.
        summary = seed_public_class_relations_layer(s)
    finally:
        event.remove(s.get_bind(), "before_cursor_execute", record)
    assert {row["name"] for row in SPEC["theorems"]} <= set(summary.theorem_names)
    assert set(statements) == {"SELECT"}


def replace_step(session, theorem_name, old_axiom, new_axiom):
    ps, fs, axs = ProofService(session), FormulaService(session), AxiomService(session)
    theorem = TheoremService(session).get_by_name(theorem_name)
    original, = ps.list_for_theorem(theorem.id)
    steps = ps.reconstruct_steps(original.id)
    old_id = axs.get_by_name(old_axiom).id
    replacement = axs.get_by_name(new_axiom)
    index = next(i for i, (step, _) in enumerate(steps) if isinstance(step, AxiomStepInput) and step.axiom_id == old_id)
    steps[index] = (AxiomStepInput(replacement.id), ps.compute_substituted_tokens(replacement.formula_id, Substitution()))
    proof = ps.create_proof(theorem.id, name="R1 proof mutation")
    with pytest.raises(ProofValidationError):
        for step, tokens in steps:
            ps.add_step(proof.id, step, fs.register(tokens).id)
        ps.validate(proof.id)
    assert proof.status != "verified"


@pytest.mark.parametrize(("theorem","old","new"), [
    ("直積:集合性", "ZF和集合公理", "hilbert_eq_refl"),
    ("MK:定義域が集合の類写像は写像", "MK類外延性公理", "ZF外延性公理"),
    ("値:特徴づけ", "ZF分出公理図式", "hilbert_eq_refl"),
    ("写像:逆像の集合性", "ZF分出公理図式", "hilbert_eq_refl"),
    ("写像:逆像の所属", "ZF内包項所属公理図式", "hilbert_eq_refl"),
    ("写像:合成は関係", "ZF分出公理図式", "hilbert_eq_refl"),
    ("写像:合成の所属", "ZF内包項所属公理図式", "hilbert_eq_refl"),
    ("写像:恒等写像は関係", "ZF分出公理図式", "hilbert_eq_refl"),
    ("写像:恒等写像の所属", "ZF内包項所属公理図式", "hilbert_eq_refl"),
])
def test_replacing_axiom_rejects_proof(fresh_seeded_session, theorem, old, new):
    replace_step(fresh_seeded_session, theorem, old, new)


@pytest.mark.parametrize(("system","axiom","theorem"), [
    ("ZF", "ZF和集合公理", "直積:集合性"),
    ("MK", "MK類外延性公理", "MK:定義域が集合の類写像は写像"),
    ("ZF", "ZF分出公理図式", "値:特徴づけ"),
    ("ZF", "パース公理", "値:集合性"),
    ("MK", "MK類内包公理図式", "類写像:値の所属"),
])
def test_removing_axiom_from_system_changes_validity(fresh_seeded_session, system, axiom, theorem):
    s = fresh_seeded_session
    axs, ps = AxiomService(s), ProofService(s)
    proof, = ps.list_for_theorem(TheoremService(s).get_by_name(theorem).id)
    sid = axs.get_system_by_name(system).id
    assert ps.is_valid_in_system(proof.id, sid)
    axs.remove_from_system(sid, axs.get_by_name(axiom).id)
    assert not ps.is_valid_in_system(proof.id, sid)


def test_unowned_symbol_is_detected(fresh_seeded_session, monkeypatch):
    from dem.db.seeds import public_packages
    from test_public_zfc_mk import assert_ownership

    s = fresh_seeded_session
    catalog = copy.deepcopy(public_packages.PACKAGE_ENTITIES)
    symbol_id = SPEC["definitions"][1]["symbol_id"]
    catalog["public_relations"]["entities"]["symbol"].remove(symbol_id)
    monkeypatch.setattr(public_packages, "PACKAGE_ENTITIES", catalog)
    s.scalar(select(Symbol).where(Symbol.public_id == symbol_id)).release_id = None
    s.flush()
    public_packages.assign_public_releases(s)
    with pytest.raises(AssertionError):
        assert_ownership(s)


@pytest.mark.parametrize(("name","guard"), [
    ("IsRelation", "IsSet(R) ∧ "), ("IsMap", "y ∈ Y ∧ "), ("ev", "IsSet(w) ∧ "),
    ("Preimage", "IsSet(x) ∧ "), ("∘", "IsSet(y) ∧ "), ("id", "x ∈ X ∧ "),
])
def test_definition_guard_mutation_changes_hash(seed_snapshot_factory, monkeypatch, name, guard):
    with seed_snapshot_factory.session("public_mk", "sqlite") as s:
        from dem.db.seeds.public_unique_existence import seed_public_unique_existence
        from dem.db.seeds.public_relations import SetRelationProofs

        seed_public_unique_existence(s)
        mutated = tuple(
            (symbol, kind, params, body.replace(guard, ""), latex, precedence)
            if symbol == name else (symbol, kind, params, body, latex, precedence)
            for symbol, kind, params, body, latex, precedence in DEFINITIONS["relations"]
        )
        monkeypatch.setitem(DEFINITIONS, "relations", mutated)
        register_definitions(s, "relations")
        expected = next(row for row in SPEC["definitions"] if row["name"] == name)
        with pytest.raises(AssertionError):
            assert_definition(s, expected)
        if name == "IsRelation":
            builder = SetRelationProofs(s, "relations")
            builder.seed_subset()
            builder.seed_product()
            with pytest.raises(ValidationError, match="proposition substitution body must be a proposition"):
                builder.seed_set_relations()
        if name == "ev":
            # Without the guard, a proper class would satisfy the uniqueness clause.
            with pytest.raises(ValidationError, match="Builder MP mismatch"):
                SetRelationProofs(s, "relations").seed_values()


def test_workspace_roundtrip_with_relations(fresh_seeded_session, tmp_path):
    from sqlalchemy.orm import Session
    from dem.db.engine import make_engine
    from scripts.workspace_import import import_workspace
    from webapi.workspace_export import WorkspaceExportMetadata, write_workspace_export

    archive = tmp_path / "relations.dempkg"
    restored = tmp_path / "restored.dempkg"
    write_workspace_export(fresh_seeded_session, archive, WorkspaceExportMetadata("test.seed", "public-relations"))
    engine = make_engine("sqlite:///" + (tmp_path / "restored.db").as_posix())
    from dem.db.models import Base
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as target:
            result = import_workspace(target, archive)
            write_workspace_export(target, restored, result.metadata)
    finally:
        engine.dispose()
    assert restored.read_bytes() == archive.read_bytes()
