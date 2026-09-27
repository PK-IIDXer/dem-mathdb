r"""DEM の DB から Lean 4 のソースを生成する。

設計: `docs/design/ops/external-verification-backtest.md`

    .\.venv\Scripts\python.exe -m scripts.backtest.export_lean --db dem_dev.db --out backtest\lean

B0 の範囲は語彙 (`Dem/Vocabulary.lean`) と公理 (`Dem/Axioms.lean`) まで。定理と証明は B1 以降。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from scripts.backtest.dem_db import (
    BacktestError,
    CONNECTIVE,
    IMPLICATION,
    PROP_BINDER,
    Symbol,
    UNIVERSAL,
    DemDatabase,
)
from scripts.backtest.formula import (
    Renderer,
    constant_name,
    constant_type,
    free_symbol_ids,
    parse,
)
from scripts.backtest.proof import (
    Formulas,
    ProofTranslator,
    Signature,
    TranslationReport,
)

THEOREMS_PER_MODULE = 40

GENERATED_HEADER = """\
-- 生成物。手で編集しないこと。
-- 生成元: scripts/backtest/export_lean.py
-- 設計:   docs/design/ops/external-verification-backtest.md
"""


def _doc_comment(text: str) -> str:
    """DEM の表示名を Lean の doc comment に入れる。区切りだけ潰す。"""
    safe = text.replace("-/", "-​/").replace("/-", "/​-")
    return f"/-- {safe} -/"


def _check_role_symbol(symbol: Symbol, role: str, type_name: str, arity: int) -> None:
    """native 化する 2 記号が期待どおりの形をしているか (設計 §4.1)。

    ここが通らなければ翻訳を中止する。前提が崩れたまま生成すると、
    Lean が通っても意味のない検査になる。
    """
    if symbol.type_name != type_name:
        raise BacktestError(
            f"symbol_role {role!r} points at {symbol.name!r} of type "
            f"{symbol.type_name!r}, expected {type_name!r}"
        )
    if symbol.arity != arity:
        raise BacktestError(
            f"symbol_role {role!r} points at {symbol.name!r} with arity "
            f"{symbol.arity}, expected {arity}"
        )


def render_vocabulary(
    symbols: dict[int, Symbol], native_ids: set[int]
) -> tuple[str, int]:
    lines = [GENERATED_HEADER, "import Dem.Prelude", "", "/-! DEM の語彙 (設計 §4.2) -/", ""]
    declared = 0
    for symbol in symbols.values():
        if symbol.is_free_variable or symbol.id in native_ids:
            continue
        lines.append(_doc_comment(f"{symbol.name}  (symbol.id = {symbol.id}, arity {symbol.arity})"))
        lines.append(f"axiom {constant_name(symbol.id)} : {constant_type(symbol)}")
        lines.append("")
        declared += 1
    return "\n".join(lines), declared


def render_axioms(db: DemDatabase, renderer: Renderer, symbols: dict[int, Symbol]) -> tuple[str, int]:
    lines = [GENERATED_HEADER, "import Dem.Vocabulary", "", "/-! DEM の公理 (設計 §4.3) -/", ""]
    count = 0
    for axiom in db.axioms():
        if not db.formula_is_proposition(axiom.formula_id):
            raise BacktestError(f"axiom {axiom.id} ({axiom.name!r}) is not a proposition")
        node = parse(db.formula_tokens(axiom.formula_id), symbols)
        binders = renderer.binders(free_symbol_ids(node, symbols))
        body = renderer.render(node)
        statement = f"∀ {binders}, {body}" if binders else body
        lines.append(_doc_comment(f"{axiom.name}  ({axiom.origin_kind}, axiom.id = {axiom.id})"))
        lines.append(f"axiom dem_ax{axiom.id} : {statement}")
        lines.append("")
        count += 1
    return "\n".join(lines), count


def _topological_order(
    theorems: list, cited: dict[int, set[int]]
) -> list:
    """`theorem` step の引用関係で並べ替える。循環は DEM 側のバグなので中止する。"""
    remaining = {theorem.id: theorem for theorem in theorems}
    emitted: set[int] = set()
    ordered = []
    while remaining:
        ready = [
            theorem
            for theorem in remaining.values()
            if cited.get(theorem.id, set()) <= emitted
        ]
        if not ready:
            raise BacktestError(
                "theorem citation graph has a cycle: "
                + ", ".join(str(theorem_id) for theorem_id in sorted(remaining))
            )
        ready.sort(key=lambda theorem: theorem.id)
        for theorem in ready:
            ordered.append(theorem)
            emitted.add(theorem.id)
            del remaining[theorem.id]
    return ordered


def render_theorems(
    translator: ProofTranslator,
    theorems: list,
    steps_by_theorem: dict[int, list],
    cited: dict[int, set[int]],
) -> list[tuple[str, str]]:
    """(モジュール名, 内容) の列。引用順に並べ、モジュールを鎖にして import する。"""
    ordered = _topological_order(theorems, cited)
    modules: list[tuple[str, str]] = []
    previous = "Dem.Axioms"
    for start in range(0, len(ordered), THEOREMS_PER_MODULE):
        chunk = ordered[start : start + THEOREMS_PER_MODULE]
        name = f"T{start // THEOREMS_PER_MODULE:03d}"
        lines = [GENERATED_HEADER, f"import {previous}", "", "set_option maxRecDepth 100000", ""]
        for theorem in chunk:
            lines.append(f"/-- {theorem.name}  (theorem.id = {theorem.id}) -/")
            lines.append(translator.translate(theorem, steps_by_theorem[theorem.id]))
            lines.append("")
        modules.append((name, "\n".join(lines)))
        previous = f"Dem.Theorems.{name}"
    return modules


def render_root(theorem_modules: list[tuple[str, str]]) -> str:
    lines = [GENERATED_HEADER, "import Dem.Vocabulary", "import Dem.Axioms"]
    lines += [f"import Dem.Theorems.{name}" for name, _ in theorem_modules]
    lines.append("")
    return "\n".join(lines)


def render_axiom_check(theorems: list, theorem_modules: list[tuple[str, str]]) -> str:
    """`#print axioms` を全定理ぶん並べたスクリプト (設計 §9)。

    `Dem/` の外に置く。ライブラリの glob に拾わせると `lake build` のたびに
    出力が流れるだけで、olean を作る意味も無い。

    root module `Dem` ではなく最後の定理モジュールを import する。モジュールは
    鎖になっているのでこれで全定理が見えるし、`lake build` が root の olean を
    作らない構成でも動く。
    """
    last = f"Dem.Theorems.{theorem_modules[-1][0]}" if theorem_modules else "Dem.Axioms"
    lines = [
        GENERATED_HEADER,
        "-- lake env lean AxiomCheck.lean で実行し、出力を scripts/backtest/check_axioms.py が読む。",
        f"import {last}",
        "",
    ]
    lines += [f"#print axioms dem_t{theorem.id}" for theorem in sorted(theorems, key=lambda t: t.id)]
    lines.append("")
    return "\n".join(lines)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _clean(out: Path) -> None:
    """前回の生成物を消す。

    選択を狭めて生成し直したとき、古いモジュールが残っていると Lean の glob が
    拾って「すでに宣言されている」「識別子が無い」の山になる。手書きの
    `Dem/Prelude.lean` には触れない。
    """
    shutil.rmtree(out / "Dem" / "Theorems", ignore_errors=True)
    for name in ("Dem.lean", "AxiomCheck.lean", "Dem/Vocabulary.lean", "Dem/Axioms.lean"):
        (out / name).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="dem_dev.db", help="読み取る DEM の DB")
    parser.add_argument("--out", default="backtest/lean", help="Lean プロジェクトの出力先")
    parser.add_argument(
        "--max-theorems",
        type=int,
        default=None,
        help="先頭から N 定理だけ翻訳する (段階的に動かすため)",
    )
    parser.add_argument(
        "--theorems",
        default=None,
        help="翻訳する定理 id をカンマ区切りで指定する。引用先は自動で閉包に含める",
    )
    args = parser.parse_args(argv)

    out = Path(args.out)
    with DemDatabase(args.db) as db:
        symbols = db.symbols()
        implication_id = db.role_symbol_id(IMPLICATION)
        universal_id = db.role_symbol_id(UNIVERSAL)
        _check_role_symbol(symbols[implication_id], IMPLICATION, CONNECTIVE, 2)
        _check_role_symbol(symbols[universal_id], UNIVERSAL, PROP_BINDER, 1)
        if not symbols[universal_id].is_quantifier:
            raise BacktestError("the universal_quantifier symbol is not a quantifier")

        renderer = Renderer(symbols, implication_id, universal_id)
        native_ids = {implication_id, universal_id}

        vocabulary, declared = render_vocabulary(symbols, native_ids)
        axioms, axiom_count = render_axioms(db, renderer, symbols)
        counts = db.counts()

        formulas = Formulas(db, symbols, renderer)
        axiom_params = {
            axiom.id: tuple(sorted(formulas.free(axiom.formula_id))) for axiom in db.axioms()
        }
        theorem_id_for_proof = db.theorem_id_for_proof()

        edges = db.citation_edges()
        theorems = db.theorems()
        if args.theorems is not None:
            wanted = {int(part) for part in args.theorems.split(",") if part.strip()}
            pending = list(wanted)
            while pending:
                current = pending.pop()
                for cited_id in edges.get(current, set()):
                    if cited_id not in wanted:
                        wanted.add(cited_id)
                        pending.append(cited_id)
            theorems = [theorem for theorem in theorems if theorem.id in wanted]
        if args.max_theorems is not None:
            theorems = theorems[: args.max_theorems]
        selected = {theorem.id for theorem in theorems}

        signatures = {
            theorem.id: Signature(
                theorem_id=theorem.id,
                params=tuple(
                    sorted(
                        formulas.free(theorem.conclusion_formula_id).union(
                            *(formulas.free(fid) for fid in theorem.premise_formula_ids)
                        )
                        if theorem.premise_formula_ids
                        else formulas.free(theorem.conclusion_formula_id)
                    )
                ),
                premise_formula_ids=theorem.premise_formula_ids,
            )
            for theorem in db.theorems()
        }

        steps_by_theorem = {theorem.id: db.steps(theorem.proof_id) for theorem in theorems}
        cited: dict[int, set[int]] = {}
        for theorem in theorems:
            references = edges.get(theorem.id, set())
            missing = references - selected
            if missing:
                raise BacktestError(
                    f"theorem {theorem.id} cites theorems outside the selection: {sorted(missing)}"
                )
            cited[theorem.id] = references

        report = TranslationReport()
        translator = ProofTranslator(
            formulas, symbols, renderer, signatures, axiom_params, theorem_id_for_proof, report
        )
        theorem_modules = render_theorems(translator, theorems, steps_by_theorem, cited)

    _clean(out)
    _write(out / "Dem" / "Vocabulary.lean", vocabulary)
    _write(out / "Dem" / "Axioms.lean", axioms)
    for name, text in theorem_modules:
        _write(out / "Dem" / "Theorems" / f"{name}.lean", text)
    _write(out / "Dem.lean", render_root(theorem_modules))
    _write(out / "AxiomCheck.lean", render_axiom_check(theorems, theorem_modules))

    free_vars = sum(1 for s in symbols.values() if s.is_free_variable)
    print(f"db            : {args.db}")
    print(f"symbol        : {counts['symbol']} (free variables {free_vars}, native 2)")
    print(f"  declared    : {declared}")
    print(f"axiom         : {axiom_count} / {counts['axiom']}")
    print(f"theorem       : {report.theorems} / {counts['theorem']}")
    print(f"proof_step    : {report.steps} / {counts['proof_step']}")
    print(f"module        : {len(theorem_modules)}")
    print(f"default use   : {len(report.default_uses)}")
    for use in report.default_uses[:20]:
        print(f"  theorem {use.theorem_id} step {use.step_ord} symbol {use.symbol_id}")
    print(f"out           : {out}")
    if declared + free_vars + len(native_ids) != counts["symbol"]:
        raise BacktestError("symbol accounting does not add up")
    if axiom_count != counts["axiom"]:
        raise BacktestError("axiom count mismatch")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BacktestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
