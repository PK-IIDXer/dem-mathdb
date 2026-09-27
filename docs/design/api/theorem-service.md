# Deus Ex Machina — TheoremService API 設計 (Phase 2)

Phase 2 で実装する `TheoremService` の API 仕様。定理ステートメント (`theorem` + `theorem_premise`) の登録・取得を担う。証明 (`proof`) は Phase 3 で実装する `ProofService` が担当する。

横断設計 (`cross-cutting.md`) および Phase 1 設計書を前提として読むこと。

---

## 責務

- `theorem` の登録・取得 (定理ステートメントのみ、証明なし)
- `theorem_premise` の管理 (順序付き前提リスト)
- theorem の `status` 管理 (`'conjecture'` → `'proven'` への昇格は Phase 3 の `ProofService` が担う)

**Phase 3 との境界**: `theorem.status = 'proven'` への昇格は `ProofService` が証明を検証した後に内部メソッド `_promote_to_proven()` を通じて行う。`TheoremService` は status を自ら変更しない。

---

## クラスシグネチャ

```python
# dem/services/theorem.py
from sqlalchemy.orm import Session
from dem.db.models.inference import Theorem
from dem.db.models.language import Formula


class TheoremService:
    def __init__(self, session: Session) -> None: ...

    # ── Theorem ───────────────────────────────────────────────────────────────

    def register(
        self,
        name: str,
        conclusion_formula_id: int,
        premise_formula_ids: list[int] | None = None,
        remarks: str | None = None,
    ) -> Theorem: ...

    def get(self, id: int) -> Theorem: ...
    def get_by_name(self, name: str) -> Theorem: ...
    def list_all(self) -> list[Theorem]: ...
    def list_premises(self, theorem_id: int) -> list[tuple[int, Formula]]: ...

    # ── 補題候補の列挙 (UX Phase 1.8) ────────────────────────────────────────

    def list_applicable(
        self, goal_formula_id: int, limit: int = 20
    ) -> list[tuple[Theorem, bool, float]]: ...

    # ── Phase 3 用内部メソッド ─────────────────────────────────────────────────

    def _promote_to_proven(self, theorem_id: int) -> None: ...
```

---

## メソッド仕様

### `register(name, conclusion_formula_id, premise_formula_ids, remarks) -> Theorem`

| 項目 | 内容 |
|---|---|
| 概要 | 定理ステートメントを登録する。`status = 'conjecture'` で固定 |
| 戻り値 | 登録した `Theorem` モデル |

`premise_formula_ids` は順序付きリスト。省略または `None` のとき前提なし (空リストと同等)。リストの添字 0 が `theorem_premise.ord = 0` に対応する。

**バリデーション**:

まず全 formula_id を**一括 SELECT** してからまとめて検証する (N+1 を避けるため)。

| 条件 | 例外 |
|---|---|
| `conclusion_formula_id` が存在しない | `NotFoundError("Formula", conclusion_formula_id)` |
| conclusion formula が「命題」でない | `ValidationError("conclusion must be a proposition")` |
| いずれかの `premise_formula_id` が存在しない | `NotFoundError("Formula", formula_id)` |
| いずれかの premise formula が「命題」でない | `ValidationError(f"premise at index {i} must be a proposition")` |
| `name` が既存 Theorem と重複 | `ConflictError("Theorem", "name", name)` |

バリデーション順序: formula の存在確認と命題チェックを先に行い、最後に name の UNIQUE チェックを行う。

**処理の流れ**:

```
1. 全 formula_id (conclusion + premises) を一括 SELECT
2. 存在確認・命題チェックを各 formula に対して実施
3. name UNIQUE チェック
4. INSERT theorem (status='conjecture')
5. INSERT theorem_premise × len(premise_formula_ids) 件 (一括 INSERT)
6. Theorem モデルを返す
```

登録された theorem のステートメント (conclusion / premises) は**不変**である。`status` / `remarks` 以外の変更 API は提供せず、DB トリガでも UPDATE を禁止する (`theorem-proof.md` の「DB 制約で表現しきれない整合性」参照)。修正したい場合は新規 theorem として登録し直す。

---

### `get(id) -> Theorem`

| 戻り値 | `Theorem` モデル |
|---|---|
| 例外 | `NotFoundError("Theorem", id)` |

---

### `get_by_name(name) -> Theorem`

| 戻り値 | `Theorem` モデル |
|---|---|
| 例外 | `NotFoundError("Theorem", name)` |

---

### `list_all() -> list[Theorem]`

全 Theorem を `id` 昇順で返す。`status` でのフィルタは行わない (conjecture も proven も含む)。0 件なら空リスト。

---

### `list_premises(theorem_id) -> list[tuple[int, Formula]]`

| 項目 | 内容 |
|---|---|
| 概要 | theorem の前提を `(ord, Formula)` のペアで `ord` 昇順に返す |
| 戻り値 | `list[tuple[int, Formula]]` (前提なしなら空リスト) |
| 例外 | `NotFoundError("Theorem", theorem_id)` |

`ord` を戻り値に含めるのは、proof_step の `'premise'` 種別が `premise_ord` で前提を参照するため。呼び出し側は「この前提を引用するには `premise_ord` に何を入れるか」を、リスト添字との暗黙の対応に頼らず明示的に得られる。

**実装**: `Theorem` モデルの `premises` リレーションには `lazy="raise"` を設定し、遅延ロードを禁止する。このメソッドが JOIN クエリで明示的に取得する。

```python
# Theorem モデル側の設定イメージ
premises: Mapped[list["TheoremPremise"]] = relationship(
    order_by="TheoremPremise.ord",
    lazy="raise",
)
```

---

### `_promote_to_proven(theorem_id) -> None` (内部)

| 項目 | 内容 |
|---|---|
| 概要 | `theorem.status` を `'proven'` に更新する |
| 呼び出し元 | `ProofService._verify_proof()` が証明の検証に成功したとき |

```sql
UPDATE theorem SET status = 'proven' WHERE id = :theorem_id
```

すでに `'proven'` のときは何もしない (冪等)。

---

### `list_applicable(goal_formula_id, limit) -> list[(Theorem, is_schematic, score)]` (UX Phase 1.8、2026-09-08)

| 項目 | 内容 |
|---|---|
| 概要 | goal に**結論が一次マッチする** proven 定理 (verified proof を持つもの) を返す |
| 戻り値 | `(Theorem, is_schematic, score)` の列。score の降順、同点は id 昇順 |
| 例外 | goal が命題でなければ `ValidationError("goal formula must be a proposition")` |

- `is_schematic` は結論の先頭が命題型自由変数であること —— 何にでもマッチする汎用補題を UI が畳めるようにする。
- score は `3·log1p(引用回数) − 2·is_schematic` の決定的な式である。**LLM は使わない。**

> **2026-09-08 修正済み ([`../ux/phase1.md`](../omitted-history.md) §5.3 D1)。** 引用回数の集計は `dict(session.execute(...).all())` とし、SQLAlchemy 2.x の `Result` を行列に確定してから辞書化する。goal と同じ結論を持つ proven 定理が候補に含まれる service テストと、`GET /theorems/applicable` の HTTP テストを追加した。
>
> D5対応では、goalと同じ先頭記号または命題型自由変数を先頭に持つ結論へSQLで絞り、引用回数も一致候補だけ集約する。全件走査との結果集合同値を回帰テストで固定した。

---

## Conjecture (予想) の運用

`status = 'conjecture'` の Theorem は証明なし状態だが、他の Theorem の **premise として参照可能**。これにより「リーマン予想を仮定すると素数定理の改良版が成立する」のような条件付き定理を表現できる。

なお `'proven'` は「検証済み proof が少なくとも 1 つ存在する」の意味であり、**公理系相対ではない**。「公理系 X の枠内で証明されているか」は `ProofService.is_valid_in_system()` (Phase 3) で判定する。

```python
# リーマン予想を conjecture として登録
riemann = theorem_svc.register(
    name="Riemann Hypothesis",
    conclusion_formula_id=riemann_formula.id,
)
# status = 'conjecture'

# リーマン予想を premise とする定理を登録
conditional = theorem_svc.register(
    name="Improved Prime Number Theorem",
    conclusion_formula_id=improved_pnt_formula.id,
    premise_formula_ids=[riemann_formula.id],
)
# この theorem は 'proven' になりうる (前提が conjecture でも)
```

---

## 使用例

### $\varphi \to \varphi$ の定理ステートメント登録

```python
from sqlalchemy.orm import Session
from dem.services.theorem import TheoremService
from dem.services.formula import FormulaService
from dem.types import Token

with Session(engine) as session:
    with session.begin():
        fml_svc = FormulaService(session)
        thm_svc = TheoremService(session)

        phi = sym_svc.get_by_name("φ")
        imp = sym_svc.get_by_name("→")

        # φ → φ を formula として登録
        phi_to_phi = fml_svc.register([
            Token(symbol_id=imp.id),
            Token(symbol_id=phi.id),
            Token(symbol_id=phi.id),
        ])

        # 前提なしの定理として登録
        thm = thm_svc.register(
            name="phi_to_phi",
            conclusion_formula_id=phi_to_phi.id,
            remarks="φ→φ (Hilbert 流で 5 ステップで証明可能)",
        )
        assert thm.status == "conjecture"
        # → Phase 3 で ProofService が証明を登録・検証すると status = "proven" になる
```

### 前提ありの定理

```python
# theorem: P(x) ⊢ ∃y. P(y)
exists_formula = fml_svc.register([...])   # ∃y. P(y)
px_formula     = fml_svc.register([...])   # P(x)

thm = thm_svc.register(
    name="px_implies_exists",
    conclusion_formula_id=exists_formula.id,
    premise_formula_ids=[px_formula.id],
)

# 前提の取得 ((ord, Formula) のペア)
premises = thm_svc.list_premises(thm.id)
assert len(premises) == 1
ord0, formula0 = premises[0]
assert ord0 == 0
assert formula0.id == px_formula.id
# proof_step の 'premise' 種別で引用するときは PremiseStepInput(premise_ord=ord0)
```

---

## 開いている論点

1. ~~**前提の不変性**~~ **【解決済み 2026-07-06】登録後不変で確定**。theorem のステートメント (conclusion / premises) は proven か否かにかかわらず登録後に変更できない。変更 API を提供しないことに加え、DB の BEFORE UPDATE トリガでも禁止する (`theorem-proof.md` の「DB 制約で表現しきれない整合性」5)。変更したい場合は新規 theorem として登録し直す。
2. **同一 formula の premise 重複**。同じ formula_id を premise に複数回登録することは制約していない (DB の `(theorem_id, ord)` PRIMARY KEY は ord が異なれば許容する)。実用上は重複する premise は不要なので、アプリ層で警告するか `ValidationError` にするか実装時に判断。
3. **`list_all()` のページング**。theorem 数が増えると `list_all()` が大量レコードを返す可能性がある。初版では全件取得で実装し、将来的に `limit` / `offset` 引数を追加する。

---

## 履歴

- 2026-04-29: 初版。
- 2026-07-06: `'proven'` が公理系相対ではないことの注記を追加 (公理系相対の判定は `ProofService.is_valid_in_system()`)。
- 2026-07-06: 設計レビュー (続き) を反映。theorem ステートメントの不変性を確定 (API 非提供 + DB トリガで担保)。開いている論点 1 を解決。
- 2026-07-06: `list_premises()` の戻り値を `list[tuple[int, Formula]]` に変更 (proof_step の `premise_ord` 参照を添字の暗黙対応に頼らないため)。
- 2026-09-08: UX Phase 1.8 の `list_applicable()` を追加。SQLAlchemy 2.x の Result 変換不具合を修正し、service / HTTP 回帰テストを追加した ([`../ux/phase1.md`](../omitted-history.md) §5.3 D1 / D7)。
