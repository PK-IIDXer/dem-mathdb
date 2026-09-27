r"""Lean の `#print axioms` と DB 側の再帰クエリを突き合わせる。

設計: `docs/design/ops/external-verification-backtest.md` §9

    .\.venv\Scripts\python.exe -m scripts.backtest.check_axioms --db dem_dev.db --project backtest\lean

型検査が通っただけでは「DEM が主張する公理系の中で証明されているか」は分からない。
そこで各定理について、Lean が報告する依存公理と、DB を辿って求めた使用公理を比べる。

DB 側は **`ProofService.list_used_axioms()` を使わず**、`proof_step` と
`applied_proof_id` の再帰クエリで独立に求める。
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from scripts.backtest.dem_db import BacktestError, DemDatabase

# Lean 自身の論理に依存した何かが混入していないか。DEM の公理だけで導かれているなら
# これらは 1 件も現れない。
FORBIDDEN = ("Classical.choice", "propext", "Quot.sound", "sorryAx")

DEPENDS = re.compile(r"^'(?P<name>[^']+)' depends on axioms: \[(?P<axioms>[^\]]*)\]")
DEPENDS_NONE = re.compile(r"^'(?P<name>[^']+)' does not depend on any axioms")
THEOREM_NAME = re.compile(r"^dem_t(?P<id>\d+)$")
AXIOM_NAME = re.compile(r"^dem_ax(?P<id>\d+)$")


@dataclass
class Result:
    checked: int = 0
    mismatches: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)
    missing_from_lean: list[int] = field(default_factory=list)
    systems: list[tuple[str, int]] = field(default_factory=list)
    """(公理系名, その体系で valid な定理数)。Lean が報告した依存だけから再計算する。"""


def run_lean(project: Path) -> str:
    lake = shutil.which("lake")
    if lake is None:
        raise BacktestError("lake is not on PATH")
    script = project / "AxiomCheck.lean"
    if not script.exists():
        raise BacktestError(f"{script} not found; run export_lean first")
    completed = subprocess.run(
        [lake, "env", "lean", script.name],
        cwd=project,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise BacktestError(
            "lean failed while printing axioms:\n" + completed.stdout + completed.stderr
        )
    return completed.stdout


def parse_lean_output(text: str) -> dict[int, set[int]]:
    """`#print axioms` の出力から、定理 id → DEM 公理 id の対応を取り出す。

    出力には語彙の `axiom` (`U` / `dem_s<id>`) も並ぶので `dem_ax<数字>` だけを拾う。
    """
    dependencies: dict[int, set[int]] = {}
    for record in _records(text):
        match = DEPENDS.match(record)
        names: list[str] = []
        if match is not None:
            names = [item.strip() for item in match.group("axioms").split(",")]
        else:
            match = DEPENDS_NONE.match(record)
            if match is None:
                continue
        theorem = THEOREM_NAME.match(match.group("name"))
        if theorem is None:
            continue
        axioms: set[int] = set()
        for name in names:
            axiom = AXIOM_NAME.match(name)
            if axiom is not None:
                axioms.add(int(axiom.group("id")))
        dependencies[int(theorem.group("id"))] = axioms
    return dependencies


def _records(text: str) -> list[str]:
    """1 定理ぶんの報告を 1 行に畳む。

    `#print axioms` は依存が多いと 1 定理の出力を複数行に折り返す。折り返し行は
    `'` で始まらないので、それを目印につなぐ。
    """
    records: list[str] = []
    current = ""
    for line in text.splitlines():
        if line.startswith("'"):
            if current:
                records.append(current)
            current = line.rstrip()
        elif current:
            current += " " + line.strip()
    if current:
        records.append(current)
    return records


def used_axioms_from_database(db: DemDatabase) -> dict[int, set[int]]:
    """DB だけで使用公理を求める。DEM のサービス層には触れない。

    `proof_step.applied_proof_id` の推移閉包を再帰 CTE で辿り、そこに現れる
    `axiom_id` を集める。`function_desc` 定義の存在一意性 proof も、DEM が
    そうしているのと同じ根拠 (記号導入を正当化する仮定) で閉包に含める。
    """
    connection = db.connection
    result: dict[int, set[int]] = {}
    for theorem in db.theorems():
        roots = {theorem.proof_id}
        axioms: set[int] = set()
        while True:
            placeholders = ",".join("?" for _ in roots)
            rows = connection.execute(
                f"""
                with recursive reachable(proof_id) as (
                    select id from proof where id in ({placeholders})
                  union
                    select s.applied_proof_id from proof_step s
                      join reachable r on r.proof_id = s.proof_id
                     where s.applied_proof_id is not null
                )
                select distinct s.axiom_id from proof_step s
                  join reachable r on r.proof_id = s.proof_id
                 where s.axiom_id is not null
                """,
                tuple(roots),
            ).fetchall()
            axioms = {row[0] for row in rows}
            if not axioms:
                break
            extra = {
                row[0]
                for row in connection.execute(
                    "select d.existence_uniqueness_proof_id from axiom a"
                    " join definition d on d.id = a.definition_id"
                    f" where a.id in ({','.join('?' for _ in axioms)})"
                    " and d.existence_uniqueness_proof_id is not null",
                    tuple(axioms),
                )
            }
            if extra <= roots:
                break
            roots |= extra
        result[theorem.id] = axioms
    return result


def check(database: str, project: Path) -> Result:
    output = run_lean(project)
    result = Result()
    for line in output.splitlines():
        for name in FORBIDDEN:
            if name in line:
                result.forbidden.append(line.strip())
    lean_dependencies = parse_lean_output(output)

    with DemDatabase(database) as db:
        expected = used_axioms_from_database(db)
        names = {axiom.id: axiom.name for axiom in db.axioms()}
        systems = db.axiom_systems()
        definition_derived = db.definition_derived_axiom_ids()

    # Lean が報告した依存だけから axiom_system メンバーシップを組み直す。
    # `is_valid_in_system()` の主張を DEM のコードに触れずに再計算していることになる。
    for system_id, system_name, members in systems:
        valid = sum(
            1
            for theorem_id, reported in lean_dependencies.items()
            if theorem_id in expected and (reported - definition_derived) <= members
        )
        result.systems.append((f"[{system_id}] {system_name}", valid))

    for theorem_id, axioms in sorted(expected.items()):
        reported = lean_dependencies.get(theorem_id)
        if reported is None:
            # 翻訳の対象外 (--max-theorems などで絞った) 定理は比較しない。
            continue
        result.checked += 1
        if reported != axioms:
            parts = []
            if reported - axioms:
                parts.append(f"lean only {[names.get(i, i) for i in sorted(reported - axioms)]}")
            if axioms - reported:
                parts.append(f"db only {[names.get(i, i) for i in sorted(axioms - reported)]}")
            result.mismatches.append(f"theorem {theorem_id}: " + ", ".join(parts))
    result.missing_from_lean = sorted(set(expected) - set(lean_dependencies))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="dem_dev.db")
    parser.add_argument("--project", default="backtest/lean")
    args = parser.parse_args(argv)

    result = check(args.db, Path(args.project))
    print(f"checked        : {result.checked} theorems")
    print(f"not translated : {len(result.missing_from_lean)}")
    print(f"mismatches     : {len(result.mismatches)}")
    for message in result.mismatches[:20]:
        print(f"  {message}")
    print(f"forbidden      : {len(result.forbidden)}")
    for message in result.forbidden[:20]:
        print(f"  {message}")
    print("valid in axiom system (Lean が報告した依存から再計算):")
    for name, count in result.systems:
        print(f"  {count:5d} / {result.checked}  {name}")
    if result.mismatches or result.forbidden:
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BacktestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
