"""DEM の DB を生 SQL だけで読む層。

設計: `docs/design/ops/external-verification-backtest.md` §1 / §4

**このパッケージは `dem` を import しない。** バックテストの独立性はそこに掛かっている。
検証は Lean のカーネルが行い、ここは変換のためにデータを取り出すだけである。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

# `symbol_type` はスキーマ層の語彙 (7 行) であり、DEM の数学コンテンツではない。
# 個々の記号を名前で同定することはしないが、この 7 種の区別だけは避けられない
# (述語記号と命題型自由変数記号は入出力の型も arity 制約も同一で、構造では分けられない)。
FUNCTION = "関数記号"
PREDICATE = "述語記号"
CONNECTIVE = "論理記号"
PROP_BINDER = "命題型量化記号"
TERM_BINDER = "項型量化記号"
FREE_TERM_VAR = "項型自由変数記号"
FREE_PROP_VAR = "命題型自由変数記号"

SYMBOL_TYPES = frozenset(
    {FUNCTION, PREDICATE, CONNECTIVE, PROP_BINDER, TERM_BINDER, FREE_TERM_VAR, FREE_PROP_VAR}
)

IMPLICATION = "implication"
UNIVERSAL = "universal_quantifier"


class BacktestError(Exception):
    """翻訳を中止すべき、DB 側の想定違反。"""


@dataclass(frozen=True)
class Symbol:
    id: int
    name: str
    arity: int
    type_name: str
    output_is_term: bool
    is_quantifier: bool

    @property
    def is_free_variable(self) -> bool:
        return self.type_name in (FREE_TERM_VAR, FREE_PROP_VAR)


@dataclass(frozen=True)
class Axiom:
    id: int
    name: str
    formula_id: int
    origin_kind: str


@dataclass(frozen=True)
class Token:
    symbol_id: int | None
    de_bruijn_index: int | None


@dataclass(frozen=True)
class Theorem:
    id: int
    name: str
    conclusion_formula_id: int
    status: str
    premise_formula_ids: tuple[int, ...]
    proof_id: int


@dataclass(frozen=True)
class Step:
    ord: int
    kind: str
    conclusion_formula_id: int
    premise_ord: int | None
    axiom_id: int | None
    applied_proof_id: int | None
    rule_kind: str | None
    gen_variable_symbol_id: int | None
    arg_step_ords: tuple[int, ...]
    term_substs: tuple[tuple[int, int], ...]
    """(source_symbol_id, target_formula_id)"""
    prop_substs: tuple[tuple[int, int, tuple[int, ...]], ...]
    """(source_symbol_id, body_formula_id, formal_param_symbol_ids)"""


class DemDatabase:
    """読み取り専用で開いた DEM の SQLite DB。"""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        if not self._path.exists():
            raise BacktestError(f"database not found: {self._path}")
        uri = f"file:{self._path.as_posix()}?mode=ro"
        self._conn = sqlite3.connect(uri, uri=True)
        self._conn.row_factory = sqlite3.Row

    @property
    def connection(self) -> sqlite3.Connection:
        """生 SQL を直接投げたい呼び出し側のための逃げ口 (読み取り専用)。"""
        return self._conn

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> DemDatabase:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # ---- 記号 -------------------------------------------------------------

    def symbols(self) -> dict[int, Symbol]:
        """全記号。`is_primitive` は読まない (設計 §4.2)。"""
        prop_type_id = self._proposition_formula_type_id()
        rows = self._conn.execute(
            """
            select s.id, s.name, s.arity,
                   st.name as type_name, st.output_formula_type_id, st.is_quantifier
              from symbol s
              join symbol_type st on st.id = s.symbol_type_id
             order by s.id
            """
        ).fetchall()
        result: dict[int, Symbol] = {}
        for row in rows:
            type_name = row["type_name"]
            if type_name not in SYMBOL_TYPES:
                raise BacktestError(f"unknown symbol_type {type_name!r} for symbol {row['id']}")
            result[row["id"]] = Symbol(
                id=row["id"],
                name=row["name"],
                arity=row["arity"],
                type_name=type_name,
                output_is_term=row["output_formula_type_id"] != prop_type_id,
                is_quantifier=bool(row["is_quantifier"]),
            )
        return result

    def role_symbol_id(self, role: str) -> int:
        row = self._conn.execute(
            "select symbol_id from symbol_role where role = ?", (role,)
        ).fetchone()
        if row is None:
            raise BacktestError(f"symbol_role {role!r} is not registered")
        return row["symbol_id"]

    def _proposition_formula_type_id(self) -> int:
        """命題型の id を、∀ の出力型として構造的に決める。

        `formula_type` の名前 (「項」「命題」) に依存しないための経路。∀ の同定は
        `symbol_role` が担うので、ここで新しい信頼点は増えない (設計 §4.1)。
        """
        row = self._conn.execute(
            """
            select st.output_formula_type_id as id
              from symbol_role r
              join symbol s on s.id = r.symbol_id
              join symbol_type st on st.id = s.symbol_type_id
             where r.role = ?
            """,
            (UNIVERSAL,),
        ).fetchone()
        if row is None:
            raise BacktestError(f"symbol_role {UNIVERSAL!r} is not registered")
        count = self._conn.execute("select count(*) as n from formula_type").fetchone()["n"]
        if count != 2:
            raise BacktestError(f"expected exactly 2 formula_type rows, found {count}")
        return row["id"]

    # ---- 公理・論理式 -----------------------------------------------------

    def axioms(self) -> list[Axiom]:
        rows = self._conn.execute(
            "select id, name, formula_id, origin_kind from axiom order by id"
        ).fetchall()
        return [
            Axiom(id=r["id"], name=r["name"], formula_id=r["formula_id"], origin_kind=r["origin_kind"])
            for r in rows
        ]

    def formula_tokens(self, formula_id: int) -> list[Token]:
        rows = self._conn.execute(
            """
            select symbol_id, de_bruijn_index
              from formula_token
             where formula_id = ?
             order by position
            """,
            (formula_id,),
        ).fetchall()
        if not rows:
            raise BacktestError(f"formula {formula_id} has no tokens")
        return [Token(r["symbol_id"], r["de_bruijn_index"]) for r in rows]

    def formula_is_proposition(self, formula_id: int) -> bool:
        prop_type_id = self._proposition_formula_type_id()
        row = self._conn.execute(
            "select formula_type_id from formula where id = ?", (formula_id,)
        ).fetchone()
        if row is None:
            raise BacktestError(f"formula {formula_id} not found")
        return row["formula_type_id"] == prop_type_id

    # ---- 定理・証明 -------------------------------------------------------

    def theorems(self) -> list[Theorem]:
        """`proven` な定理と、それを支える `verified` proof。

        1 定理に複数の proof がありうるので、最小の proof.id を採る。どれを採っても
        検査の意味は変わらない (どれか 1 本が通れば定理は導出できている)。
        """
        premises: dict[int, list[tuple[int, int]]] = {}
        for row in self._conn.execute(
            "select theorem_id, ord, formula_id from theorem_premise order by theorem_id, ord"
        ):
            premises.setdefault(row["theorem_id"], []).append((row["ord"], row["formula_id"]))

        rows = self._conn.execute(
            """
            select t.id, t.name, t.conclusion_formula_id, t.status, min(p.id) as proof_id
              from theorem t
              join proof p on p.theorem_id = t.id and p.status = 'verified'
             where t.status = 'proven'
             group by t.id
             order by t.id
            """
        ).fetchall()
        result = []
        for row in rows:
            ordered = premises.get(row["id"], [])
            if [ord_ for ord_, _ in ordered] != list(range(len(ordered))):
                raise BacktestError(f"theorem {row['id']} has non-contiguous premise ordinals")
            result.append(
                Theorem(
                    id=row["id"],
                    name=row["name"],
                    conclusion_formula_id=row["conclusion_formula_id"],
                    status=row["status"],
                    premise_formula_ids=tuple(fid for _, fid in ordered),
                    proof_id=row["proof_id"],
                )
            )
        return result

    def theorem_id_for_proof(self) -> dict[int, int]:
        return {
            row["id"]: row["theorem_id"]
            for row in self._conn.execute("select id, theorem_id from proof")
        }

    def axiom_systems(self) -> list[tuple[int, str, frozenset[int]]]:
        """(id, 名前, member の axiom id 集合)。"""
        members: dict[int, set[int]] = {}
        for row in self._conn.execute(
            "select axiom_system_id, axiom_id from axiom_system_member"
        ):
            members.setdefault(row["axiom_system_id"], set()).add(row["axiom_id"])
        return [
            (row["id"], row["name"], frozenset(members.get(row["id"], set())))
            for row in self._conn.execute("select id, name from axiom_system order by id")
        ]

    def definition_derived_axiom_ids(self) -> frozenset[int]:
        """定義公理は object theory の仮定ではなく保存的な足場なので、体系判定から外す。

        DEM の `is_valid_in_system()` と同じ扱い。根拠まで含めたいときは
        `function_desc` の存在一意性 proof を閉包に入れる (§9)。
        """
        return frozenset(
            row["id"]
            for row in self._conn.execute("select id from axiom where definition_id is not null")
        )

    def citation_edges(self) -> dict[int, set[int]]:
        """定理 id → その proof が `theorem` step で引用する定理 id。"""
        edges: dict[int, set[int]] = {}
        for row in self._conn.execute(
            """
            select citing.theorem_id as citing, cited.theorem_id as cited
              from proof_step s
              join proof citing on citing.id = s.proof_id
              join proof cited on cited.id = s.applied_proof_id
             where s.applied_proof_id is not null
            """
        ):
            edges.setdefault(row["citing"], set()).add(row["cited"])
        return edges

    def steps(self, proof_id: int) -> list[Step]:
        args: dict[int, list[int]] = {}
        for row in self._conn.execute(
            """
            select step_ord, referenced_step_ord from proof_step_arg
             where proof_id = ? order by step_ord, arg_ord
            """,
            (proof_id,),
        ):
            args.setdefault(row["step_ord"], []).append(row["referenced_step_ord"])

        term_substs: dict[int, list[tuple[int, int]]] = {}
        for row in self._conn.execute(
            """
            select step_ord, source_symbol_id, target_formula_id from proof_step_subst_term
             where proof_id = ? order by step_ord, source_symbol_id
            """,
            (proof_id,),
        ):
            term_substs.setdefault(row["step_ord"], []).append(
                (row["source_symbol_id"], row["target_formula_id"])
            )

        params: dict[tuple[int, int], list[int]] = {}
        for row in self._conn.execute(
            """
            select step_ord, source_symbol_id, formal_param_symbol_id
              from proof_step_subst_prop_param
             where proof_id = ? order by step_ord, source_symbol_id, ord
            """,
            (proof_id,),
        ):
            params.setdefault((row["step_ord"], row["source_symbol_id"]), []).append(
                row["formal_param_symbol_id"]
            )

        prop_substs: dict[int, list[tuple[int, int, tuple[int, ...]]]] = {}
        for row in self._conn.execute(
            """
            select step_ord, source_symbol_id, body_formula_id from proof_step_subst_prop
             where proof_id = ? order by step_ord, source_symbol_id
            """,
            (proof_id,),
        ):
            key = (row["step_ord"], row["source_symbol_id"])
            prop_substs.setdefault(row["step_ord"], []).append(
                (row["source_symbol_id"], row["body_formula_id"], tuple(params.get(key, [])))
            )

        rows = self._conn.execute(
            """
            select s.ord, s.step_kind, s.conclusion_formula_id, s.premise_ord, s.axiom_id,
                   s.applied_proof_id, s.gen_variable_symbol_id, r.kind as rule_kind
              from proof_step s
              left join inference_rule r on r.id = s.inference_rule_id
             where s.proof_id = ?
             order by s.ord
            """,
            (proof_id,),
        ).fetchall()
        return [
            Step(
                ord=row["ord"],
                kind=row["step_kind"],
                conclusion_formula_id=row["conclusion_formula_id"],
                premise_ord=row["premise_ord"],
                axiom_id=row["axiom_id"],
                applied_proof_id=row["applied_proof_id"],
                rule_kind=row["rule_kind"],
                gen_variable_symbol_id=row["gen_variable_symbol_id"],
                arg_step_ords=tuple(args.get(row["ord"], [])),
                term_substs=tuple(term_substs.get(row["ord"], [])),
                prop_substs=tuple(prop_substs.get(row["ord"], [])),
            )
            for row in rows
        ]

    def counts(self) -> dict[str, int]:
        """レポート用の総数 (設計 §7)。"""
        out: dict[str, int] = {}
        for table in ("symbol", "axiom", "formula", "theorem", "proof", "proof_step"):
            out[table] = self._conn.execute(f"select count(*) as n from {table}").fetchone()["n"]
        return out
