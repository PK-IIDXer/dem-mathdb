import json
from pathlib import Path

import pytest
from sqlalchemy import event, select

from dem.db.models import Package, PackageRelease, Proof, Symbol, Theorem
from dem.db.seeds import seed_all
from dem.db.seeds import public_algebra
from dem.db.seeds.public_algebra import AlgebraProofs, STATEMENTS, register_definitions
from dem.errors import ProofValidationError, ValidationError
from dem.services.axiom import AxiomService
from dem.services.formula import FormulaService
from dem.services.package import check_release_dependencies, publish_release
from dem.services.proof import ProofService
from dem.services.symbol import symbol_shape
from dem.services.theorem import TheoremService

from test_public_relations_maps import assert_definition, replace_step

SEED_PHASE = "public_algebra"
SPEC = json.loads((Path(__file__).parent / "fixtures/public-algebra-spec.json").read_text(encoding="utf-8"))
# The existing releases keep the digests pinned by the relations spec; this spec adds algebra only.
EXISTING_DIGESTS = json.loads((Path(__file__).parent / "fixtures/public-relations-maps-spec.json")
                              .read_text(encoding="utf-8"))["digests"]


def test_definitions_and_notation(fresh_seeded_session):
    s = fresh_seeded_session
    for definition in SPEC["definitions"]:
        assert_definition(s, definition)
    formula = FormulaService(s)
    for dss in ("op(m, op(m, x, y), z) = op(m, x, op(m, y, z))", "IsMonoid(S, m, e)"):
        tokens = formula.parse_text(dss)[0]
        assert formula.parse_text(formula.print_text(tokens))[0] == tokens
    shapes = {}
    for symbol in s.scalars(select(Symbol)):
        assert symbol_shape(symbol) not in shapes, (symbol.name, shapes.get(symbol_shape(symbol)))
        shapes[symbol_shape(symbol)] = symbol.name


def test_statements_proof_dependencies_and_systems(fresh_seeded_session):
    s = fresh_seeded_session
    fs, ps, ts = FormulaService(s), ProofService(s), TheoremService(s)
    axs = AxiomService(s)
    systems = {name: axs.get_system_by_name(name).id for name in SPEC["systems"]}
    assert [row["name"] for row in SPEC["theorems"]] == [name for name, _, _ in STATEMENTS]
    for expected, (_, premises, conclusion) in zip(SPEC["theorems"], STATEMENTS, strict=True):
        theorem = ts.get_by_name(expected["name"])
        proof, = ps.list_for_theorem(theorem.id)
        assert (theorem.public_id, fs.get(theorem.conclusion_formula_id).hash) == (expected["id"], expected["hash"])
        tokens = fs.parse_text(expected["dss"])[0]
        assert tokens == ps._tokens_for_formula(theorem.conclusion_formula_id) == fs.parse_text(conclusion)[0]
        assert [(form.hash, ps._tokens_for_formula(form.id)) for _, form in ts.list_premises(theorem.id)] == [
            (p["hash"], fs.parse_text(p["dss"])[0]) for p in expected["premises"]
        ] == [(p["hash"], fs.parse_text(text)[0]) for p, text in zip(expected["premises"], premises, strict=True)]
        assert proof.status == "verified"
        assert len(ps.list_steps(proof.id)) == expected["steps"] <= 200
        assert [name for name, sid in systems.items() if ps.is_valid_in_system(proof.id, sid)] == expected["valid"]
        assert sorted(a.name for a in ps.list_used_axioms(proof.id)) == expected["axioms"]
        assert not {"パース公理", "ZF選択公理"} & set(expected["axioms"])


def test_frozen_releases(fresh_seeded_session):
    s = fresh_seeded_session
    from test_public_zfc_mk import assert_ownership
    assert_ownership(s)
    actual = {}
    for release in s.scalars(select(PackageRelease).order_by(PackageRelease.id)):
        assert not check_release_dependencies(s, release.id)
        name = s.get(Package, release.package_id).name
        actual[f"{name}@{release.version}"] = publish_release(s, release.id).content_digest
    assert actual == {**EXISTING_DIGESTS, **SPEC["digests"]}
    assert len(actual) == len(EXISTING_DIGESTS) + 1
    algebra = s.scalar(select(PackageRelease).join(Package).where(Package.name == "dem.public.algebra"))
    assert algebra.manifest["depends"] == {"dem.public.relations": "=2.0.0"}
    owned = set(s.scalars(select(Theorem.name).where(Theorem.release_id == algebra.id)))
    assert owned == {name for name, _, _ in STATEMENTS}


def test_seed_all_returns_with_selects(fresh_seeded_session):
    s = fresh_seeded_session
    s.connection()
    statements = []

    def record(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement.lstrip().split()[0].upper())

    event.listen(s.get_bind(), "before_cursor_execute", record)
    try:
        summary = seed_all(s)
    finally:
        event.remove(s.get_bind(), "before_cursor_execute", record)
    assert {row["name"] for row in SPEC["theorems"]} <= set(summary.theorem_names)
    assert set(statements) == {"SELECT"}


@pytest.mark.parametrize(("theorem", "old", "new"), [
    # M4: the one-point semigroup proof needs the purity axiom for its elements.
    ("半群:一点半群", "ZF純粋性公理", "hilbert_eq_refl"),
    # M9: uniqueness of the identity chains two identity laws by equality.
    ("モノイド:単位元の一意性", "等号代入公理", "hilbert_eq_refl"),
    ("演算:値の所属", "op 定義公理", "IsSemigroup 定義公理"),
])
def test_replacing_axiom_rejects_proof(fresh_seeded_session, theorem, old, new):
    replace_step(fresh_seeded_session, theorem, old, new)


@pytest.mark.parametrize(("system", "axiom", "theorem"), [
    # M5: the empty semigroup identifies ∅ × ∅ with ∅ by extensionality.
    ("ZF", "ZF外延性公理", "半群:空半群"),
    ("ZFC", "ZF分出公理図式", "演算:値の所属"),
    ("MK", "ZF純粋性公理", "モノイド:一点モノイド"),
])
def test_removing_axiom_from_system_changes_validity(fresh_seeded_session, system, axiom, theorem):
    s = fresh_seeded_session
    axs, ps = AxiomService(s), ProofService(s)
    proof, = ps.list_for_theorem(TheoremService(s).get_by_name(theorem).id)
    sid = axs.get_system_by_name(system).id
    assert ps.is_valid_in_system(proof.id, sid)
    axs.remove_from_system(sid, axs.get_by_name(axiom).id)
    assert not ps.is_valid_in_system(proof.id, sid)


def test_unowned_algebra_symbol_is_detected(fresh_seeded_session, monkeypatch):
    import copy
    from dem.db.seeds import public_packages
    from test_public_zfc_mk import assert_ownership

    s = fresh_seeded_session
    catalog = copy.deepcopy(public_packages.PACKAGE_ENTITIES)
    symbol_id = SPEC["definitions"][1]["symbol_id"]
    catalog["public_algebra"]["entities"]["symbol"].remove(symbol_id)
    monkeypatch.setattr(public_packages, "PACKAGE_ENTITIES", catalog)
    s.scalar(select(Symbol).where(Symbol.public_id == symbol_id)).release_id = None
    s.flush()
    public_packages.assign_public_releases(s)
    with pytest.raises(AssertionError):
        assert_ownership(s)


def _seed_until_failure(session):
    proofs = AlgebraProofs(session, public_algebra.PACKAGE)
    for step in (proofs.seed_operations, proofs.seed_semigroups, proofs.seed_examples, proofs.seed_monoids):
        step()


@pytest.mark.parametrize(("name", "old", "new", "failing"), [
    # M1: commutativity in place of associativity.
    ("IsSemigroup", "op(m, op(m, x, y), z) = op(m, x, op(m, y, z))", "op(m, x, y) = op(m, y, x)", "半群:結合律"),
    # M2: no sethood of the carrier.
    ("IsSemigroup", "IsSet(S) ∧ (IsMap(m, S × S, S) ∧ ", "(IsMap(m, S × S, S) ∧ ", "半群:台の集合性"),
    # M3: the operation applied to the swapped pair.
    ("op", "ev(m, ⟨,⟩(x, y))", "ev(m, ⟨,⟩(y, x))", "演算:値の所属"),
    # M6: no membership of the identity, which would make ∅ a monoid.
    ("IsMonoid", "(e ∈ S ∧ ", "(", "モノイド:単位元の所属"),
    # M7: only a left identity.
    ("IsMonoid", "(op(m, e, x) = x ∧ op(m, x, e) = x)", "op(m, e, x) = x", "モノイド:左単位律"),
    # M8: no semigroup clause.
    ("IsMonoid", "IsSemigroup(S, m) ∧ (e ∈ S ∧ ", "(e ∈ S ∧ ", "モノイド:半群である"),
])
def test_definition_mutation_is_rejected(seed_snapshot_factory, monkeypatch, name, old, new, failing):
    mutated = []
    for symbol, kind, params, body, latex in public_algebra.DEFINITIONS:
        if symbol == name:
            assert body.count(old) == 1
            body = body.replace(old, new)
        mutated.append((symbol, kind, params, body, latex))
    monkeypatch.setattr(public_algebra, "DEFINITIONS", tuple(mutated))
    with seed_snapshot_factory.session("public_class_relations", "sqlite") as s:
        register_definitions(s)
        expected = next(row for row in SPEC["definitions"] if row["name"] == name)
        with pytest.raises(AssertionError):
            assert_definition(s, expected)
        with pytest.raises((ValidationError, ProofValidationError, ValueError)):
            _seed_until_failure(s)
        names = [statement for statement, _, _ in STATEMENTS]
        index = names.index(failing)
        proved = set(s.scalars(select(Theorem.name).join(Proof, Proof.theorem_id == Theorem.id)
                               .where(Proof.status == "verified")))
        assert set(names[:index]) <= proved
        assert failing not in proved


def test_workspace_roundtrip_with_algebra(fresh_seeded_session, tmp_path):
    from sqlalchemy.orm import Session
    from dem.db.engine import make_engine
    from dem.db.models import Base
    from scripts.workspace_import import import_workspace
    from webapi.workspace_export import WorkspaceExportMetadata, write_workspace_export

    archive = tmp_path / "algebra.dempkg"
    restored = tmp_path / "restored.dempkg"
    write_workspace_export(fresh_seeded_session, archive, WorkspaceExportMetadata("test.seed", "public-algebra"))
    engine = make_engine("sqlite:///" + (tmp_path / "restored.db").as_posix())
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as target:
            result = import_workspace(target, archive)
            write_workspace_export(target, restored, result.metadata)
    finally:
        engine.dispose()
    assert restored.read_bytes() == archive.read_bytes()
