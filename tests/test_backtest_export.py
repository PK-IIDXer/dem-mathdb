"""外部検証バックテストの Lean 生成器 (B0 の範囲) のテスト。

設計: `docs/design/ops/external-verification-backtest.md`

翻訳器は `dem` を import してはならない (設計 §1)。**このテストは import してよい** ——
検査されるのは翻訳器であって、テストではない。
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from dem.db.models.language import Symbol
from dem.db.seeds._variable_pool import variable_name
from scripts.backtest import export_lean
from scripts.backtest.dem_db import BacktestError, DemDatabase

# 論理コアだけで足りる。記号・公理の翻訳は上位層に依存しない。
SEED_PHASE = "l0"
SEED_DATABASE = "sqlite"

BACKTEST_SOURCES = sorted(Path("scripts/backtest").glob("*.py"))


def _database_path(session: Session) -> str:
    url = session.get_bind().url
    assert url.database is not None
    return url.database


def _symbol_ids(session: Session) -> dict[str, int]:
    return {row.name: row.id for row in session.scalars(select(Symbol))}


def test_backtest_sources_do_not_import_dem() -> None:
    """独立性の第一原則 (設計 §1) を静的に固定する。"""
    assert BACKTEST_SOURCES, "scripts/backtest に翻訳器が無い"
    for path in BACKTEST_SOURCES:
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            assert not stripped.startswith("import dem"), f"{path}:{lineno} imports dem"
            assert not stripped.startswith("from dem"), f"{path}:{lineno} imports dem"


def test_export_accounts_for_every_symbol_and_axiom(
    seeded_session: Session, tmp_path: Path
) -> None:
    export_lean.main(["--db", _database_path(seeded_session), "--out", str(tmp_path)])

    assert (tmp_path / "Dem.lean").exists()
    assert (tmp_path / "Dem" / "Vocabulary.lean").exists()
    assert (tmp_path / "Dem" / "Axioms.lean").exists()

    with DemDatabase(_database_path(seeded_session)) as db:
        symbols = db.symbols()
        axioms = db.axioms()
        # native の 2 記号は symbol_role から取る (テストも記号名では同定しない)
        native = {db.role_symbol_id("implication"), db.role_symbol_id("universal_quantifier")}

    vocabulary = (tmp_path / "Dem" / "Vocabulary.lean").read_text(encoding="utf-8")
    declared = {
        line.split()[1] for line in vocabulary.splitlines() if line.startswith("axiom ")
    }
    free_variables = {s.id for s in symbols.values() if s.is_free_variable}

    expected = {
        f"dem_s{s.id}"
        for s in symbols.values()
        if not s.is_free_variable and s.id not in native
    }
    assert declared == expected
    # 自由変数記号と native の 2 つ以外がすべて宣言されている
    assert len(declared) + len(free_variables) + len(native) == len(symbols)

    statements = (tmp_path / "Dem" / "Axioms.lean").read_text(encoding="utf-8")
    for axiom in axioms:
        assert f"axiom dem_ax{axiom.id} :" in statements


def test_logical_core_axioms_translate_faithfully(
    seeded_session: Session, tmp_path: Path
) -> None:
    """信頼できるのは Lean の型検査だけなので、翻訳そのものは golden で固定する。"""
    export_lean.main(["--db", _database_path(seeded_session), "--out", str(tmp_path)])
    statements = {
        line.split(" : ", 1)[0].removeprefix("axiom "): line.split(" : ", 1)[1]
        for line in (tmp_path / "Dem" / "Axioms.lean").read_text(encoding="utf-8").splitlines()
        if line.startswith("axiom dem_ax")
    }

    ids = _symbol_ids(seeded_session)
    phi, psi, chi = (f"v{ids[name]}" for name in ("φ", "ψ", "χ"))
    phi1 = f"v{ids['φ¹']}"
    x, y, t = (f"v{ids[variable_name(name)]}" for name in ("x", "y", "t"))
    eq = f"dem_s{ids['=']}"

    def statement(axiom_name: str) -> str:
        with DemDatabase(_database_path(seeded_session)) as db:
            for axiom in db.axioms():
                if axiom.name == axiom_name:
                    return statements[f"dem_ax{axiom.id}"]
        raise AssertionError(f"axiom {axiom_name!r} not found")

    # K: φ → (ψ → φ)
    assert statement("ヒルベルト公理K") == (
        f"∀ ({phi} : Prop) ({psi} : Prop), ({phi} → ({psi} → {phi}))"
    )
    # S: (φ → (ψ → χ)) → ((φ → ψ) → (φ → χ))
    assert statement("ヒルベルト公理S") == (
        f"∀ ({phi} : Prop) ({psi} : Prop) ({chi} : Prop), "
        f"(({phi} → ({psi} → {chi})) → (({phi} → {psi}) → ({phi} → {chi})))"
    )
    # ∀除去: (∀ z, φ¹ z) → φ¹ t
    assert statement("全称除去公理") == (
        f"∀ ({phi1} : U → Prop) ({t} : U), "
        f"((∀ z0 : U, ({phi1} z0)) → ({phi1} {t}))"
    )
    # Leibniz: x = y → (φ¹ x → φ¹ y)
    assert statement("等号代入公理") == (
        f"∀ ({phi1} : U → Prop) ({x} : U) ({y} : U), "
        f"(({eq} {x} {y}) → (({phi1} {x}) → ({phi1} {y})))"
    )
    # 定数命題の全称導入: φ → ∀ _z, φ  (束縛子が本体で使われない)
    assert statement("定数命題の全称導入公理") == (
        f"∀ ({phi} : Prop), ({phi} → (∀ _z0 : U, {phi}))"
    )
def test_export_aborts_without_symbol_role(seeded_session: Session, tmp_path: Path) -> None:
    """native 化する 2 記号を同定できないなら、生成してはならない (設計 §4.1)。"""
    tampered = tmp_path / "tampered.db"
    shutil.copy(_database_path(seeded_session), tampered)
    connection = sqlite3.connect(tampered)
    connection.execute("delete from symbol_role where role = 'implication'")
    connection.commit()
    connection.close()

    with pytest.raises(BacktestError, match="implication"):
        export_lean.main(["--db", str(tampered), "--out", str(tmp_path / "out")])


def test_export_aborts_when_role_symbol_has_unexpected_shape(
    seeded_session: Session, tmp_path: Path
) -> None:
    tampered = tmp_path / "reshaped.db"
    shutil.copy(_database_path(seeded_session), tampered)
    connection = sqlite3.connect(tampered)
    # implication の役割を ¬ (論理記号だが arity 1) に付け替える
    connection.execute(
        "update symbol_role set symbol_id = (select id from symbol where name = '¬')"
        " where role = 'implication'"
    )
    connection.commit()
    connection.close()

    with pytest.raises(BacktestError, match="arity"):
        export_lean.main(["--db", str(tampered), "--out", str(tmp_path / "out")])


def test_export_aborts_when_role_symbol_has_wrong_type(
    seeded_session: Session, tmp_path: Path
) -> None:
    tampered = tmp_path / "retyped.db"
    shutil.copy(_database_path(seeded_session), tampered)
    connection = sqlite3.connect(tampered)
    # universal_quantifier の役割を ∃ ではなく ¬ (論理記号) に付け替える
    connection.execute(
        "update symbol_role set symbol_id = (select id from symbol where name = '¬')"
        " where role = 'universal_quantifier'"
    )
    connection.commit()
    connection.close()

    with pytest.raises(BacktestError, match="expected"):
        export_lean.main(["--db", str(tampered), "--out", str(tmp_path / "out")])
