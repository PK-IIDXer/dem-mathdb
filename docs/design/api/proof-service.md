# Deus Ex Machina — ProofService API 設計 (Phase 3)

Phase 3 で実装する `ProofService` の API 仕様。証明 (`proof`) の作成・ステップ追加・検証を担う。本フェーズで最もアルゴリズム的に複雑なサービスであり、代入操作 (`apply_substitution`) と汎化操作 (`abstract_and_quantify`) の pure 関数が核心となる。

横断設計 (`cross-cutting.md`) および Phase 1〜2 設計書を前提として読むこと。

---

## 責務

- `inference_rule` の読み取り (シードデータ: MP / Gen の 2 行)
- `proof` の作成・取得
- `proof_step` のステップ単位追加 (構造と導出結論を検証)
- `proof` の論理的正当性検証 (`validate()`)
  - 検証成功時: `proof.status = 'verified'` → `TheoremService._promote_to_proven()` を呼ぶ
  - 検証失敗時: `proof.status = 'rejected'` → `ProofValidationError` を raise
- 証明執筆補助ヘルパー (`compute_substituted_tokens`, `compute_gen_tokens`)
- 公理依存クエリ (`list_used_axioms`, `is_valid_in_system`) — README の「公理系を入れ替えて影響範囲をトレースする」中核機能

---

## Phase 3 で types.py に追記する型

### 代入型

```python
# dem/types.py に追記

@dataclass(frozen=True)
class TermSubst:
    """項型自由変数 x への代入: x ↦ target_formula (項)"""
    source_symbol_id: int   # 項型自由変数記号の symbol.id
    target_formula_id: int  # 代入先の項 formula.id

@dataclass(frozen=True)
class PropSubst:
    """
    命題型自由変数 φ への代入: φ(a1,...,an) ↦ body[a1/x1,...,an/xn]
    formal_param_symbol_ids は body 内の形式パラメータの symbol.id を
    「φ の引数列と対応する順序」で並べたもの。
    """
    source_symbol_id: int                    # 命題型自由変数記号の symbol.id
    body_formula_id: int                     # 代入する命題 formula.id
    formal_param_symbol_ids: tuple[int, ...] # 形式パラメータ (項型自由変数記号 IDs, ord 順)

@dataclass(frozen=True)
class Substitution:
    """
    axiom / theorem 適用時の代入指定。
    適用順は prop_substs → term_substs の順 (theorem-proof.md の規定通り)。
    空の場合は空タプルを渡す。
    """
    prop_substs: tuple[PropSubst, ...]
    term_substs: tuple[TermSubst, ...]
```

### 証明ステップ入力型

```python
@dataclass(frozen=True)
class PremiseStepInput:
    """theorem の前提リストから 1 件を引用する"""
    premise_ord: int  # theorem_premise.ord

@dataclass(frozen=True)
class AxiomStepInput:
    """公理を代入付きで適用する"""
    axiom_id: int
    subst: Substitution

@dataclass(frozen=True)
class TheoremStepInput:
    """検証済みの proof を pin して、その theorem を代入付きで適用する"""
    applied_proof_id: int           # pin する proof の id (theorem は proof.theorem_id から辿る)
    subst: Substitution
    arg_step_ords: tuple[int, ...]  # theorem の各 premise を提供する過去 step の ord (ord 対応順)

@dataclass(frozen=True)
class MPStepInput:
    """Modus Ponens: antecedent_step と implication_step から consequent を導く"""
    antecedent_step_ord: int   # φ を導いた past step の ord
    implication_step_ord: int  # φ→ψ を導いた past step の ord

@dataclass(frozen=True)
class GenStepInput:
    """Generalization: body_step の命題 φ から ∀x.φ を導く"""
    body_step_ord: int           # φ を導いた past step の ord
    gen_variable_symbol_id: int  # ∀ で束縛する項型自由変数記号の symbol.id

# Union 型
ProofStepInput = (
    PremiseStepInput | AxiomStepInput | TheoremStepInput | MPStepInput | GenStepInput
)
```

`MP` / `Gen` の推論規則 ID は `ProofService` が内部で `inference_rule` テーブルから引く。呼び出し側は `MPStepInput` / `GenStepInput` という型で意図を表明するだけでよい。

---

## クラスシグネチャ

```python
# dem/services/proof.py
from sqlalchemy.orm import Session
from dem.db.models.inference import Axiom, InferenceRule, Proof, ProofStep
from dem.types import (
    Token, SymbolMeta,
    Substitution, ProofStepInput,
)


class ProofService:
    def __init__(self, session: Session) -> None: ...

    # ── InferenceRule (read-only seed data) ───────────────────────────────────

    def get_inference_rule(self, id: int) -> InferenceRule: ...
    def get_inference_rule_by_name(self, name: str) -> InferenceRule: ...
    def list_inference_rules(self) -> list[InferenceRule]: ...

    # ── Proof ─────────────────────────────────────────────────────────────────

    def create_proof(
        self,
        theorem_id: int,
        name: str | None = None,
        remarks: str | None = None,
    ) -> Proof: ...

    def get(self, id: int) -> Proof: ...
    def list_for_theorem(self, theorem_id: int) -> list[Proof]: ...

    # ── ProofStep ─────────────────────────────────────────────────────────────

    def add_step(
        self,
        proof_id: int,
        step_input: ProofStepInput,
        conclusion_formula_id: int | None = None,
    ) -> ProofStep: ...

    def list_steps(self, proof_id: int) -> list[ProofStep]: ...

    # ── 証明状態と決定的 follow-up (UX Phase 2.1 / 2.4) ────────────────────

    def get_state(self, proof_id: int) -> ProofState: ...

    def list_step_followups(
        self,
        proof_id: int,
        step_ord: int,
        max_depth: int = 3,
    ) -> list[ProofStepFollowup]: ...

    # ── 執筆補助: 代入と引数の推定 (UX Phase 1.8) ─────────────────────────────

    def suggest_step(
        self,
        proof_id: int,
        *,
        kind: str,                       # 'axiom' | 'theorem'
        applied_theorem_id: int | None = None,
        axiom_id: int | None = None,
        arg_step_ords: Sequence[int] = (),
        goal_tokens: list[Token] | None = None,
    ) -> dict[str, object]: ...

    # ── Validation ────────────────────────────────────────────────────────────

    def validate(self, proof_id: int) -> None: ...

    # ── 公理依存クエリ ─────────────────────────────────────────────────────────

    def list_used_axioms(self, proof_id: int) -> list[Axiom]: ...
    def is_valid_in_system(self, proof_id: int, axiom_system_id: int) -> bool: ...

    # ── 証明執筆補助ヘルパー ───────────────────────────────────────────────────

    def compute_substituted_tokens(
        self,
        formula_id: int,
        subst: Substitution,
    ) -> list[Token]: ...

    def compute_gen_tokens(
        self,
        body_formula_id: int,
        gen_variable_symbol_id: int,
    ) -> list[Token]: ...
```

---

## メソッド仕様

### InferenceRule 系

`get_inference_rule` / `get_inference_rule_by_name` / `list_inference_rules` は FormulaType 系と同じ構造。存在しない場合は `NotFoundError`。

---

### `create_proof(theorem_id, name, remarks) -> Proof`

| 項目 | 内容 |
|---|---|
| 概要 | proof を作成する。`status = 'draft'` で固定 |
| 戻り値 | `Proof` モデル (ステップなし) |
| 例外 | `NotFoundError("Theorem", theorem_id)` |

同一 theorem に複数の proof を登録できる。`name` は NULL 許容。

---

### `add_step(proof_id, step_input, conclusion_formula_id) -> ProofStep`

| 項目 | 内容 |
|---|---|
| 概要 | proof にステップを 1 件追加する。既存の検証カーネルで結論を導出し、指定された結論と一致した場合だけ保存する |
| 戻り値 | 追加した `ProofStep` モデル。`ord` は自動採番 (既存最大 ord + 1、初ステップは 0) |

**追加時の構造バリデーション**:

| 条件 | 例外 |
|---|---|
| `proof_id` が存在しない | `NotFoundError("Proof", proof_id)` |
| `proof.status` が `'draft'` でない | `ValidationError("cannot add steps to a non-draft proof")` |
| `conclusion_formula_id` が存在しない | `NotFoundError("Formula", conclusion_formula_id)` |
| conclusion formula が「命題」でない | `ValidationError("conclusion must be a proposition")` |
| `AxiomStepInput`: `axiom_id` が存在しない | `NotFoundError("Axiom", axiom_id)` |
| `TheoremStepInput`: `applied_proof_id` が存在しない | `NotFoundError("Proof", applied_proof_id)` |
| `MPStepInput` / `GenStepInput` / `TheoremStepInput`: arg_step_ord が現在 ord 以上 | `ValidationError("arg_step_ord must reference a prior step")` |
| `GenStepInput`: `gen_variable_symbol_id` が項型自由変数記号でない | `ValidationError("gen_variable must be a term-free-variable symbol")` |
| `AxiomStepInput` / `TheoremStepInput`: subst の source が正しい SymbolType でない (`TermSubst`: 項型自由変数記号 / `PropSubst`: 命題型自由変数記号) | `ValidationError(...)` |
| `PropSubst.formal_param_symbol_ids` の個数が source の arity と不一致、項型自由変数記号でないものを含む、または**重複がある** | `ValidationError(...)` |

**追加時の論理検証 (UX Phase 0、2026-09-06)**: 構造検査後、`validate_proof_step` で導出する。代入後の結論、MP の前件、定理引用の引数、Gen の自由変数条件もこの時点で検証する。未検証の proof の引用は `proof.unverified_citation`、結論不一致は `proof.step_conclusion_mismatch` として拒否する。失敗時にはステップやその引数・代入行を挿入せず、proof は draft のままにする。

**`conclusion_formula_id` は省略できる (UX Phase 1.7、2026-09-08)**。省略した場合、カーネルが導出した結論をそのまま `FormulaService.register` で intern して保存する。指定した場合の挙動は従来どおりで、導出結果と一致しなければ `proof.step_conclusion_mismatch` になる。

**`AssumptionStepInput` だけは必須のままである** —— 仮定の結論は入力そのものであり、導出する対象が無い。省略すると `ValidationError(code="proof.assumption_needs_conclusion")`。

最終的な仮定の解消と定理の結論との一致は引き続き `validate()` が確認する。seed 用の `add_raw_steps` は一括保存後に `validate()` で検証する経路を維持する。

> 実装上の注意: 結論を省略した呼び出しでも `StepData` を組むために命題式が 1 件必要なので、定理の結論式を placeholder として読む。`validate_proof_step` は仮定以外で `conclusion_tokens` を参照しないため照合には影響しない。

追加済みステップの判定と依存関係をトランザクション内で再利用する。新しいトランザクションでは過去のステップを一度だけ再検証し、rollback または既存の証明データの編集時にはキャッシュを破棄する。

`ProofValidationError` は従来の `message` / `step_ord` に加え、任意の `code` / `details` を持つ。HTTP は 422 と既存の `detail` / `step_ord` を維持し、結論不一致では `details.expected.tokens`、`details.actual.tokens`、最初に異なる子ノードの添字列 `details.diff_path` を返す。token は `position` / `symbol_id` / `de_bruijn_index` を持ち、描画文字列は含めない。

---

### `suggest_step(proof_id, *, kind, ...) -> dict` (UX Phase 1.8、2026-09-08)

| 項目 | 内容 |
|---|---|
| 概要 | 適用する公理・定理と、選んだ引数ステップ (と任意の goal) から、代入・引数候補・導出される結論を一次マッチングで推定する |
| 戻り値 | `applied_proof_id` / `subst` (`Substitution`) / `undetermined` / `defaulted_to_identity` / `conclusion_tokens` / `premise_count` / `arg_candidates` |

- マッチングは `demlang.match`。schema 変数は項型自由変数と 0 引数の命題型自由変数。1 引数の命題型自由変数は**引数が束縛変数である場合だけ** (Miller pattern) 解く。
- 決まらなかった変数は `undetermined` に、パターンに現れるが制約が無かった変数は `defaulted_to_identity` に入れて返す。UI が「N 件中 M 件を自動決定」を出せるようにするための分離である。
- `arg_candidates` は各 premise について、代入後の premise と結論が一致する既存ステップの ord 一覧。
- **提案が誤っていてもカーネルが `add_step` で弾くので健全性は落ちない。** ここで測るのは UX の質である。

> **副作用がある。** `TermSubst` / `PropSubst` は代入先をformula idで指すため、提案中に式を冪等internする。代入編集・計算・step永続化の共通契約を保つため、D9では書き込みauthoring commandとして維持する判断をした。read-only許可リストには入れない ([`../ux/phase1.md`](../omitted-history.md) §5.3 D9)。

> `StepForm`はPhase 1にProofStateが無い間、最終結論を誤ってgoalにせず、選択済み前提だけで照合する。goalなしtheorem代入の回復を確認した ([`../ux/phase1.md`](../omitted-history.md) §5.3 D2 / D6)。

---

### `POST /proofs/{id}/steps/suggest-backward` (UX N7、2026-09-18)

top-down の hole goal に対し、公理または verified proof を持つ定理の結論を左から最大 3 回
`A → rest` に分解し、`rest` を既存 DSS matcher で照合する authoring endpoint。入力は
`kind`、`axiom_id` または `applied_theorem_id`、必須 `goal_tokens`、任意の `subst` 上書き。
深さ 0〜3 の一致を浅い順にすべて返し、同一 recipe は除く。深さ 4 は探索しない。

候補は `match_depth`、`subst`、`application_conclusion_tokens`、MP を外す順の
`antecedent_goals` と `intermediate_conclusions`、`undetermined`、`defaulted_to_identity` を持つ。
定理候補は `applied_proof_id`、`premise_count`、`premise_goals`、`arg_candidates` も返す。
既存 `suggest_step` に具体化した全結論を渡すため、substitution body の intern、verified proof の選択、
引数候補の規則は既存契約と同一である。応答は plan を保存せず、client が既存 axiom / theorem / MP
node へ写す。formula を intern し得るため read-only 許可リストには入れない。

---

### `validate(proof_id) -> None`

| 項目 | 内容 |
|---|---|
| 概要 | proof の全ステップを論理的に検証する |
| 戻り値 | `None` |
| 副作用 (成功時) | `proof.status = 'verified'` / `TheoremService._promote_to_proven(theorem_id)` |
| 副作用 (失敗時) | `proof.status = 'rejected'` |
| 例外 | `NotFoundError("Proof", proof_id)` / `ProofValidationError(message, step_ord)` |

**冪等性**:
- `proof.status == 'verified'` → 即座に `None` を返す (再検証しない)
- `proof.status == 'rejected'` または `'draft'` → 全ステップを再検証する

**処理の流れ** (詳細は後述「validate の内部構造」):

```
1. proof / theorem / premises / goal を DB から取得
2. 全 proof_step を ord 順に取得
3. 全代入データ (subst_term, subst_prop, subst_prop_param) を一括プリロード
4. 全 proof_step_arg を一括プリロード
5. 全 formula.hash を必要分だけ一括 SELECT
6. 各ステップを順に validate_proof_step_pure() で検証
7. 最終ステップが goal と一致するか確認
8. proof.status = 'verified' に UPDATE
9. TheoremService._promote_to_proven(theorem_id) を呼ぶ
```

---

### `list_steps(proof_id) -> list[ProofStep]`

| 戻り値 | `list[ProofStep]` を `ord` 昇順で返す |
|---|---|
| 例外 | `NotFoundError("Proof", proof_id)` |

`ProofStep` モデルの関連テーブル (`proof_step_arg`, `proof_step_subst_*`) には `lazy="raise"` を設定し、遅延ロードを禁止する。

---

### `get_state(proof_id) -> ProofState` (UX Phase 2.1、2026-09-09)

draft proof の goal、定理の premises、確立済み step、未解消の仮定、goal 到達状況を返す。
draft は `_prior_judgements` で既存の検証カーネルを replay し、その判定結果を公開形へ変換する。
同じ式を複数回 assume した場合は、カーネルと同じく token 列を依存キーとして扱う。

verified proof は step を replay せず、goal と premises、`reached_goal=true` を返す。
rejected proof も replay せず、goal と premises、`reached_goal=false`、
`blocking=["validation_failed"]` を返す。HTTP は `GET /proofs/{id}/state`。

---

### `list_step_followups(proof_id, step_ord, max_depth=3)` (UX Phase 2.4、2026-09-09)

指定 step の結論が含意 `A → B` であり、`A` と一致する既存 step がある場合に、
MP step の候補を返す。`B` が含意なら同じ判定を繰り返すが、深さは 3 以下に固定する。
候補は保存せず、受け入れ時には通常の `add_step(MPStepInput(...))` を必ず通す。
HTTP は `GET /proofs/{id}/steps/{ord}/followups`。サービス API は先読み用途のため深さ 3 までを
保つが、**HTTP は `max_depth=1` を明示して、要求した実在 step を含意側に持つ候補だけを返す。**
深い候補の `implication_step_ord` はまだ存在しない予測 step を指す一方、それを使うクライアントは
なく、frontend も候補を 1 step ずつ受理するたびに取り直すためである。

---

### `list_used_axioms(proof_id) -> list[Axiom]`

| 項目 | 内容 |
|---|---|
| 概要 | proof が推移的に依存する全 axiom を返す。`'theorem'` ステップが pin する proof (`applied_proof_id`) を再帰的に辿る |
| 戻り値 | `list[Axiom]` (`id` 昇順、重複なし) |
| 例外 | `NotFoundError("Proof", proof_id)` |

**実装**: 再帰 CTE 1 本 (`axiom.md` の「典型的な運用クエリ」参照)。

```sql
WITH RECURSIVE reachable_proof(proof_id) AS (
  SELECT :proof_id
  UNION
  SELECT ps.applied_proof_id
  FROM proof_step ps
  JOIN reachable_proof rp ON ps.proof_id = rp.proof_id
  WHERE ps.step_kind = 'theorem'
)
SELECT DISTINCT a.*
FROM proof_step ps
JOIN reachable_proof rp ON ps.proof_id = rp.proof_id
JOIN axiom a ON a.id = ps.axiom_id
WHERE ps.step_kind = 'axiom'
ORDER BY a.id;
```

verified proof は immutable かつ引用グラフは DAG なので、この再帰は必ず停止する。

---

### `is_valid_in_system(proof_id, axiom_system_id) -> bool`

| 項目 | 内容 |
|---|---|
| 概要 | proof が推移的に使用する axiom がすべて指定の公理系に含まれるか判定する。README の「公理系を入れ替えて影響範囲をトレースする」中核機能 |
| 戻り値 | `True` / `False` |
| 例外 | `NotFoundError("Proof", proof_id)` / `NotFoundError("AxiomSystem", axiom_system_id)` |

**実装**: `list_used_axioms` の CTE と `axiom_system_member` の `EXCEPT` を組み合わせた 1 クエリ。

```sql
SELECT NOT EXISTS (
  SELECT axiom_id FROM (/* list_used_axioms の CTE */) used
  EXCEPT
  SELECT axiom_id FROM axiom_system_member WHERE axiom_system_id = :axiom_system_id
);
```

判定結果は DB に保存しない。axiom_system のメンバーシップ変更で陳腐化するため、常にオンザフライで計算する。

---

### `compute_substituted_tokens(formula_id, subst) -> list[Token]`

| 項目 | 内容 |
|---|---|
| 概要 | formula に代入 `subst` を適用した後の token 列を返す。DB 書き込みなし |
| 用途 | 証明執筆時に「axiom/theorem に代入するとどの formula になるか」を確認するヘルパー |
| 戻り値 | `list[Token]` |
| 例外 | `NotFoundError("Formula", formula_id)` など |

呼び出し側のパターン:

```python
tokens = proof_svc.compute_substituted_tokens(k_axiom.formula_id, subst=σ)
formula = formula_svc.register(tokens)   # → conclusion_formula_id に使う
proof_svc.add_step(proof_id, AxiomStepInput(k_axiom.id, σ), formula.id)
```

---

### `compute_gen_tokens(body_formula_id, gen_variable_symbol_id) -> list[Token]`

| 項目 | 内容 |
|---|---|
| 概要 | Gen を適用したときの結果 (`∀x.φ`) の token 列を返す。DB 書き込みなし |
| 用途 | Gen ステップ追加前に conclusion formula を登録するためのヘルパー |
| 戻り値 | `list[Token]` |
| 例外 | `NotFoundError("Formula", body_formula_id)` / `NotFoundError("Symbol", gen_variable_symbol_id)` |

---

## validate の内部構造

`validate()` の本体ロジックは**モジュールレベル純粋関数**として分離する。DB 依存はプリロード段階で解消し、アルゴリズム部分を DB なしでテスト可能にする。

### プリロード (DB 読み取り)

`validate()` は検証開始前に以下をすべて一括取得する。N+1 クエリを起こさないことが目的。

| データ | 取得方法 |
|---|---|
| theorem + premises (Formula tokens 含む) | JOIN クエリ |
| goal formula tokens | JOIN クエリ |
| `'theorem'` ステップが pin する proof (status) とその theorem の conclusion / premises tokens | `proof.id IN (...)` 一括 + JOIN |
| 全 proof_step (ord 順) | `WHERE proof_id = ?` |
| 全 proof_step_arg | `WHERE proof_id = ?` → dict[step_ord → list[referenced_step_ord]] |
| 全 proof_step_subst_term | `WHERE proof_id = ?` |
| 全 proof_step_subst_prop + prop_param | `WHERE proof_id = ?` |
| 各ステップの conclusion formula tokens | `formula.id IN (...)` 一括 |
| 代入対象の formula tokens (subst の body / target) | `formula.id IN (...)` 一括 |
| 関連 symbol の SymbolMeta | `symbol.id IN (...)` 一括 |
| 役割付き symbol (→ / ∀) の id | `symbol_role` から取得。初期化時キャッシュ可 |

プリロード後、全データは純粋なデータ構造 (dict / list / Token) として純粋関数に渡される。

### モジュールレベル純粋関数

#### `validate_proof_steps()`

```python
# dem/services/proof.py (クラス定義の外)

def validate_proof_steps(
    goal_tokens: list[Token],
    premise_tokens_list: list[list[Token]],  # theorem premises (ord 順)
    steps_data: list[StepData],              # 全 proof_step のデータ (ord 順)
    symbol_meta: dict[int, SymbolMeta],
    quantifier_symbol_ids: QuantifierIds,    # symbol_role 由来: ∀ ('universal_quantifier') / → ('implication') の symbol.id
) -> None:
    """
    全ステップを検証する pure 関数。
    失敗時: ProofValidationError(message, step_ord=...) を raise。
    成功時: None。
    """
```

`StepData` は proof_step + 関連データをまとめた pure dataclass:

```python
@dataclass(frozen=True)
class StepData:
    ord: int
    step_kind: str
    conclusion_tokens: list[Token]
    # step_kind ごとのデータ (None if not applicable)
    premise_ord: int | None
    axiom_tokens: list[Token] | None
    applied_proof_status: str | None                           # pin された proof の status
    applied_theorem_conclusion_tokens: list[Token] | None      # pin された proof の theorem から取得
    applied_theorem_premise_tokens_list: list[list[Token]] | None
    subst_prop: dict[int, tuple[list[Token], tuple[int, ...]]] | None  # symbol_id → (body_tokens, formal_params)
    subst_term: dict[int, list[Token]] | None                          # symbol_id → target_tokens
    arg_step_ords: list[int]     # referenced prior step ords
    gen_variable_symbol_id: int | None
    inference_rule_kind: str | None  # 'modus_ponens' or 'generalization'
```

自然推論の `∀` 導入を Gen-backed macro として扱うため、validation 中の「過去ステップ」は token 列だけでなく、どの theorem premise に依存しているかも持つ。

```python
@dataclass(frozen=True)
class StepJudgement:
    tokens: list[Token]
    premise_deps: frozenset[int]
```

依存集合は pure validation 中に計算する。

| step_kind | `premise_deps` |
|---|---|
| `'premise'` | `{premise_ord}` |
| `'axiom'` | `frozenset()` |
| `'theorem'` | 引数 step の依存集合の和集合 |
| `'rule'` (MP) | 2 引数 step の依存集合の和集合 |
| `'rule'` (Gen) | body step の依存集合を引き継ぐ |

#### `validate_proof_step()`

各ステップを検証し、**そのステップが導くべき token 列**を返す。

```python
def validate_proof_step(
    step: StepData,
    prior: dict[int, StepJudgement],  # {ord: judgement} — 検証済み過去ステップ
    premise_tokens_list: list[list[Token]],
    symbol_meta: dict[int, SymbolMeta],
    quantifier_symbol_ids: QuantifierIds,
) -> StepJudgement:
    """
    Returns:
        このステップが論理的に導く formula の token 列と premise 依存集合
    Raises:
        ProofValidationError (step.ord 付き)
    """
```

| step_kind | 検証内容 | 返す token 列 |
|---|---|---|
| `'premise'` | `premise_ord` が範囲内か | `StepJudgement(premise_tokens_list[premise_ord], {premise_ord})` |
| `'axiom'` | (なし — 代入の正当性は result を conclusion と照合して保証) | `StepJudgement(apply_substitution_pure(...), ∅)` |
| `'theorem'` | pin された applied_proof が `'verified'` か / arg 数と前提数が一致するか / 各 arg が instantiated premise と一致するか | `StepJudgement(apply_substitution_pure(conclusion_tokens, ...), union(arg deps))` |
| `'rule'` (MP) | imp の最外が `→` か / antecedent と arg[0] が一致するか | `StepJudgement(imp の右辺, union(arg deps))` |
| `'rule'` (Gen) | x が body step の依存 premise に自由出現しないか | `StepJudgement(abstract_and_quantify_pure(...), body deps)` |

Gen の side condition は、従来の「theorem の全 premise」ではなく body step が依存する premise のみを検査する。

```python
for premise_ord in body_judgement.premise_deps:
    if has_free_occurrence(premise_tokens_list[premise_ord], x_id):
        raise ProofValidationError("Gen variable is free in a dependent theorem premise", step.ord)
```

検証後、返った token 列のハッシュと `step.conclusion_tokens` のハッシュを比較する。不一致なら `ProofValidationError`。

`'theorem'` ステップで引用先証明の Gen 側条件を σ 適用後に再検査しない根拠 (locally nameless により変数捕獲が構造的に不可能) は、`theorem-proof.md` の「『theorem』適用の健全性 (一様代入のメタ定理)」を参照。この健全性は `apply_substitution_pure` / `abstract_and_quantify_pure` の shifting の正しさを前提とするため、両関数のテストには捕獲が起きないことを確認するケースを必ず含める。

---

### モジュールレベル純粋関数 (代入・汎化操作)

#### `apply_substitution_pure()`

```python
def apply_substitution_pure(
    formula_tokens: list[Token],
    prop_subst: dict[int, tuple[list[Token], tuple[int, ...]]],
    term_subst: dict[int, list[Token]],
    symbol_meta: dict[int, SymbolMeta],
) -> list[Token]:
    """
    代入操作の pure 実装。
    1. prop_subst を先に適用 (φ(a1,...,an) → body[a1/x1,...,an/xn])
    2. term_subst を後に適用 (x → target_tokens)
    locally nameless の depth shifting を伴う。
    """
```

**prop_subst の適用 (walk_and_replace_prop_vars)**:

token 列を左から走査する。命題型自由変数 `φ` (arity n) の出現
`φ(t₁, ..., tₙ)` を見つけたら、各 `tᵢ` を完全な項部分木として読む:
1. `prop_subst[φ.id] = (body_tokens, [x₁, ..., xₙ])` を取得
2. 元の実引数部分木 `tᵢ` 内へ prop pass を再帰適用する
3. `body_tokens` 内の `xᵢ` への自由 Symbol 参照を処理済みの `tᵢ` で置き換える
4. 実引数部分木全体へ、body 内の挿入位置に応じた de Bruijn shifting を適用する
5. 置き換えた結果を出力列に追加し、挿入した body は同じ prop pass で再走査しない

**term_subst の適用 (walk_and_replace_term_vars)**:

token 列を走査し、項型自由変数 `x` の Symbol 参照を `term_subst[x.id]` で置き換える。`target_tokens` が de Bruijn index を含む場合は現在のスコープ深度に合わせて shift する。

**同時代入の規定** (`theorem-proof.md` の「代入の意味論」参照): 各 pass は 1 回の走査による**同時代入**であり、置き換えで出力に挿入された token をその pass では再走査しない。ただし、置換前の formula に存在した命題 call site の実引数部分木は元の構文木の一部なので、挿入前に同じ prop map で再帰処理する。symbol ごとの逐次置換ループは誤実装 ($\sigma = \{x \mapsto y,\ y \mapsto z\}$ で $x$ が $z$ まで連鎖してしまい、結果が代入の記述順に依存する)。pass 順は prop → term で固定。prop pass の formal param はその pass で消費されるため結果に残らない。詳細は `propositional-schema-term-arguments.md`。

#### `abstract_and_quantify_pure()`

```python
def abstract_and_quantify_pure(
    body_tokens: list[Token],
    variable_symbol_id: int,
    forall_symbol_id: int,
    symbol_meta: dict[int, SymbolMeta],
) -> list[Token]:
    """
    Gen の結果 ∀x.φ を構築する pure 関数。
    body_tokens 内の variable_symbol_id への自由 Symbol 参照を、その出現位置の
    スコープ深度 d に応じた de Bruijn index d に置き換え、先頭に ∀ を付与して返す。
    既存の de Bruijn index は一切変更しない。
    (深度の追跡に量化記号の判定と arity が要るため symbol_meta を受け取る。
     forall_symbol_id は symbol_role の 'universal_quantifier' から引く。)
    """
```

**処理の流れ**:
1. `body_tokens` を構文構造に沿って走査し、各位置のスコープ深度 d (そこまでに入った量化記号スコープの数) を追跡する。量化記号のスコープは「その直後の 1 引数サブツリー」なので、深度追跡には単純な線形スキャンではなく arity に基づくスタック走査が必要 (`symbol_meta` を使う)
2. `variable_symbol_id` への Symbol 参照を `Token(de_bruijn_index=d)` に置き換える。新しく付与する ∀ は body 全体の外側に付くため、深度 d の位置から見た距離はちょうど d になる
3. **既存の de Bruijn index は変更しない**。それらは body 内部の束縛子を指しており、外側に束縛子を 1 つ足しても「出現から束縛子までの距離」は変わらない
4. 先頭に `Token(symbol_id=forall_symbol_id)` を付与して返す

**注意 (旧仕様の誤り)**: 「x を ▢₀ に置き換えて既存 index を +1 する」という手続きは誤り。例えば body = `[∀, P, ▢₀]` (= ∀z.P(z)、x は非出現) に Gen を適用すると、旧手続きでは `[∀, ∀, P, ▢₁]` (= ∀y.∀z.P(**y**)) という別の論理式になってしまう。正しい結果は `[∀, ∀, P, ▢₀]` (= ∀y.∀z.P(z))。

---

## 使用例: $\varphi \to \varphi$ の証明

Hilbert 流 5 ステップ証明 (K 公理 + S 公理)。

```python
from sqlalchemy.orm import Session
from dem.services.proof import ProofService
from dem.services.formula import FormulaService
from dem.services.theorem import TheoremService
from dem.types import Substitution, PropSubst, AxiomStepInput, MPStepInput

with Session(engine) as session:
    with session.begin():
        fml_svc  = FormulaService(session)
        thm_svc  = TheoremService(session)
        prf_svc  = ProofService(session)

        # 前提: φ, ψ, χ (命題型自由変数), →, φ→φ の formula が登録済みとする
        phi      = sym_svc.get_by_name("φ")
        psi      = sym_svc.get_by_name("ψ")
        chi      = sym_svc.get_by_name("χ")
        phi2phi  = fml_svc.get_by_hash(...)   # φ→φ の formula
        k_axiom  = axm_svc.get_by_name("K")   # φ → ψ → φ
        s_axiom  = axm_svc.get_by_name("S")   # (φ→ψ→χ) → (φ→ψ) → (φ→χ)

        # theorem: ⊢ φ→φ (前提なし)
        thm = thm_svc.register("phi_to_phi", conclusion_formula_id=phi2phi.id)

        # proof を作成
        proof = prf_svc.create_proof(thm.id)

        # --- step 0: S 公理に σ = {ψ↦φ→φ, χ↦φ} を代入 ---
        phi_to_phi_formula = fml_svc.get_by_hash(...)   # φ→φ
        σ0 = Substitution(
            prop_substs=(
                PropSubst(psi.id, phi_to_phi_formula.id, formal_param_symbol_ids=()),
                PropSubst(chi.id, fml_svc.get_by_hash(...).id, formal_param_symbol_ids=()),  # φ
            ),
            term_substs=(),
        )
        step0_tokens = prf_svc.compute_substituted_tokens(s_axiom.formula_id, σ0)
        step0_formula = fml_svc.register(step0_tokens)
        # step0_formula: (φ→(φ→φ)→φ) → ((φ→(φ→φ)) → (φ→φ))
        prf_svc.add_step(proof.id, AxiomStepInput(s_axiom.id, σ0), step0_formula.id)

        # --- step 1: K 公理に σ = {ψ↦φ→φ} を代入 ---
        σ1 = Substitution(
            prop_substs=(PropSubst(psi.id, phi_to_phi_formula.id, formal_param_symbol_ids=()),),
            term_substs=(),
        )
        step1_tokens  = prf_svc.compute_substituted_tokens(k_axiom.formula_id, σ1)
        step1_formula = fml_svc.register(step1_tokens)
        # step1_formula: φ → (φ→φ) → φ
        prf_svc.add_step(proof.id, AxiomStepInput(k_axiom.id, σ1), step1_formula.id)

        # --- step 2: MP(step1, step0) ---
        step2_tokens  = ... # (φ→(φ→φ)) → (φ→φ) — step0 の consequent を compute_substituted_tokens 等で取得
        step2_formula = fml_svc.register(step2_tokens)
        prf_svc.add_step(proof.id, MPStepInput(1, 0), step2_formula.id)
        #   antecedent_step_ord=1 (step1 が φ→(φ→φ)→φ を導いている)
        #   implication_step_ord=0 (step0 が (φ→(φ→φ)→φ)→... の形)

        # --- step 3: K 公理に σ = {ψ↦φ} を代入 ---
        σ3 = Substitution(
            prop_substs=(PropSubst(psi.id, fml_svc.get_by_hash(...).id, formal_param_symbol_ids=()),),
            term_substs=(),
        )
        step3_tokens  = prf_svc.compute_substituted_tokens(k_axiom.formula_id, σ3)
        step3_formula = fml_svc.register(step3_tokens)
        # step3_formula: φ → (φ→φ)
        prf_svc.add_step(proof.id, AxiomStepInput(k_axiom.id, σ3), step3_formula.id)

        # --- step 4: MP(step3, step2) → φ→φ ---
        prf_svc.add_step(proof.id, MPStepInput(3, 2), phi2phi.id)

        # 検証
        prf_svc.validate(proof.id)
        # → proof.status = 'verified', thm.status = 'proven'
```

---

## 開いている論点

1. **`StepData` の設計の複雑さ**。純粋関数に渡す `StepData` が多くのフィールドを持つ。実装時に named tuple や dataclass で簡潔にまとめるか、step_kind ごとのサブクラスにするか検討する。後者の方が isinstance によるパターンマッチが明確になる。
2. **`applied_proof.status` チェックのタイミング**。`add_step()` 時に `TheoremStepInput.applied_proof_id` が `'verified'` かを確認するか、`validate()` 時のみに確認するか。前者はユーザーへの早期フィードバックになるが、まだ検証していない proof を仮に引用して証明を組み立てるケース (実験的な執筆) を妨げる。当初は `validate()` 時のみに確認していたが、UX Phase 0 (2026-09-06) で `add_step()` 時にも拒否する方式に変更した。
3. **depth shifting の実装詳細**。`apply_substitution_pure` と `abstract_and_quantify_pure` の depth shifting アルゴリズムは locally nameless の標準手続きだが、コーナーケース (入れ子スコープ、代入ターゲットが自身も束縛変数を含む場合) の扱いは実装時に詳細を詰める。`formula.md` の代入操作概略を参照のこと。
4. **代入結果 formula の登録タイミング**。`validate()` は代入結果を in-memory で計算して hash 比較するだけでよいが、`compute_substituted_tokens()` + `FormulaService.register()` を呼ぶと DB に formula が増える。巨大な証明では代入結果の formula が大量に登録される可能性がある。キャッシュや重複排除 (hash UNIQUE) が自然に機能するのでまず問題ないが、ストレージ消費には注意。
5. **`validate()` の途中失敗と `status='rejected'`**。`ProofValidationError` を raise する前に `proof.status = 'rejected'` を UPDATE するか否か。UPDATE してから raise することで、例外をキャッチしなくても DB を見れば失敗を確認できる。本設計ではこの方針を採用する。

---

## 履歴

- 2026-04-29: 初版。
  - Phase 3 追加型 (TermSubst, PropSubst, Substitution, 5 種の StepInput) を定義。
  - validate() を DB プリロード + pure 関数 (validate_proof_steps / apply_substitution_pure / abstract_and_quantify_pure) に分離する構造を確立。
  - φ→φ の 5 ステップ証明例を追加。
- 2026-07-06: 設計レビューを反映。
  - `abstract_and_quantify_pure()` の仕様を修正 (出現深度 d に応じた ▢_d 方式。既存 index は不変。旧仕様の誤りを反例付きで明記)。
  - `TheoremStepInput.applied_theorem_id` を `applied_proof_id` に変更 (proof pinning)。
  - 公理依存クエリ `list_used_axioms()` / `is_valid_in_system()` を追加。
  - → / ∀ の特定を `symbol_role` 経由に変更。
- 2026-07-06: 設計レビュー (続き) を反映。
  - 同時代入の規定を明記 (pass 内再代入の禁止、逐次置換ループが誤実装であること)。
  - `add_step()` に代入の構造バリデーション (source の SymbolType、formal param の個数・型・重複禁止) を追加。
  - 一様代入の健全性メタ定理への参照と、捕獲防止テストの必須化を明記。
- 2026-09-08: UX Phase 1 を反映。`add_step` の `conclusion_formula_id` を Optional
  にし (仮定のみ必須)、代入と引数を推定する `suggest_step` を追加した。
  `suggest_step` の副作用と現状の制約は [`../ux/phase1.md`](../omitted-history.md) §5.3 を参照。
- 2026-09-09: UX Phase 2.1 / 2.4 を反映。`get_state` と
  `list_step_followups` を追加した。
- 2026-09-17: followups の HTTP 境界を深さ 1 に限定した。サービス API の深さ 3 の探索は維持する。
- 2026-09-18: top-down hole の後件照合を行う `suggest-backward` HTTP endpoint を追加した。
- 2026-09-09: Phase 2.1-a を修正。rejected proof は replay せず
  `validation_failed` を返す契約に訂正した。
