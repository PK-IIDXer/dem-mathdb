"""公理依存クロスチェックのうち、Lean を起動せずに固定できる部分のテスト。

設計: `docs/design/ops/external-verification-backtest.md` §9

Lean を実際に走らせる部分は `tests/test_backtest_mutations.py` と同じく
`DEM_BACKTEST_LEAN=1` のときだけ走る。ここで固定するのは出力の読み取りと、
DB 側の再帰クエリが `ProofService` を使わずに同じ答えを出すことである。
"""

from __future__ import annotations

import os
import shutil

import pytest
from sqlalchemy.orm import Session

from dem.services.proof import ProofService
from scripts.backtest.check_axioms import parse_lean_output, used_axioms_from_database
from scripts.backtest.dem_db import DemDatabase

SEED_PHASE = "l0"
SEED_DATABASE = "sqlite"


def _database_path(session: Session) -> str:
    url = session.get_bind().url
    assert url.database is not None
    return url.database


def test_wrapped_print_axioms_output_is_parsed() -> None:
    """`#print axioms` は依存が多いと 1 定理の出力を折り返す。

    折り返しを畳まずに読むと、大きい定理が黙って比較対象から落ちる。
    """
    text = "\n".join(
        [
            "'dem_t1' depends on axioms: [dem_ax1, dem_ax2]",
            "'dem_t40' depends on axioms: [dem_ax1,",
            " dem_ax10,",
            " dem_ax2,",
            " U,",
            " dem_s3]",
            "'dem_t7' does not depend on any axioms",
            "'someOther' depends on axioms: [dem_ax99]",
        ]
    )
    assert parse_lean_output(text) == {
        1: {1, 2},
        40: {1, 10, 2},
        7: set(),
    }


def test_forbidden_axioms_are_visible_in_the_output() -> None:
    """Lean 自身の論理に依存したら報告に現れる、という前提そのものを固定する。"""
    text = "'dem_t1' depends on axioms: [Classical.choice, dem_ax1]"
    assert parse_lean_output(text) == {1: {1}}
    assert "Classical.choice" in text


def test_database_closure_matches_the_service(seeded_session: Session) -> None:
    """DB 側の再帰クエリが `ProofService.list_used_axioms()` と一致する。

    バックテスト本体はサービス層を使わないが、**独立に書いた再帰クエリが同じ答えを
    出すこと自体**は確かめておく価値がある。ここが食い違えば、突き合わせの
    「DB 側」がそもそも DEM の主張を表していない。
    """
    database = _database_path(seeded_session)
    with DemDatabase(database) as db:
        computed = used_axioms_from_database(db)
        theorems = {theorem.id: theorem.proof_id for theorem in db.theorems()}

    service = ProofService(seeded_session)
    assert computed == {}
    assert theorems == {}
    for theorem_id, proof_id in theorems.items():
        expected = {axiom.id for axiom in service.list_used_axioms(proof_id)}
        assert computed[theorem_id] == expected, f"theorem {theorem_id}"


@pytest.mark.skipif(shutil.which("lake") is None, reason="Lean toolchain (lake) not on PATH")
@pytest.mark.skipif(
    not os.environ.get("DEM_BACKTEST_LEAN"),
    reason="set DEM_BACKTEST_LEAN=1 to run the Lean-backed check",
)
def test_axiom_cross_check_passes_for_the_generated_project() -> None:
    """生成済みの `backtest/lean` に対して突き合わせが通ることを確認する。

    先に `export_lean` と `lake build` を済ませておく必要がある。
    """
    from pathlib import Path

    from scripts.backtest.check_axioms import check

    project = Path("backtest/lean")
    if not (project / "AxiomCheck.lean").exists():
        pytest.skip("backtest/lean が生成されていない")
    database = Path(os.environ.get("DEM_BACKTEST_DB") or "dem_dev.db")
    if not database.exists():
        pytest.skip(f"backtest database not found: {database}")
    with DemDatabase(database) as db:
        expected_checked = len(db.theorems())
    result = check(str(database), project)
    assert result.mismatches == []
    assert result.forbidden == []
    assert result.checked == expected_checked
