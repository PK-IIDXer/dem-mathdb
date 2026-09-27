# Deus Ex Machina — AxiomService API 設計 (Phase 2)

Phase 2 で実装する `AxiomService` の API 仕様。公理 (`axiom`) の登録・取得と、公理系 (`axiom_system`) の管理を担う。

横断設計 (`cross-cutting.md`) および Phase 1 設計書を前提として読むこと。

---

## 責務

- `axiom` の登録・取得 (Phase 2 では `origin_kind = 'primitive'` のみ)
- `axiom_system` の登録・取得
- `axiom_system_member` を通じた公理系メンバーシップの管理
- 公理系の包含関係クエリ (`X ⊆ Y` 判定)

**Phase 4 との境界**: `origin_kind = 'definition_derived'` の axiom 登録は `DefinitionService` が内部メソッド `_register_definition_derived()` を呼ぶ形で行う。Phase 2 の公開 API はすべて primitive 公理を対象とする。

---

## クラスシグネチャ

```python
# dem/services/axiom.py
from sqlalchemy.orm import Session
from dem.db.models.inference import Axiom, AxiomSystem


class AxiomService:
    def __init__(self, session: Session) -> None: ...

    # ── Axiom ─────────────────────────────────────────────────────────────────

    def register(
        self,
        name: str,
        formula_id: int,
        remarks: str | None = None,
    ) -> Axiom: ...

    def get(self, id: int) -> Axiom: ...
    def get_by_name(self, name: str) -> Axiom: ...
    def list_axioms(self) -> list[Axiom]: ...

    # ── AxiomSystem ───────────────────────────────────────────────────────────

    def register_system(
        self,
        name: str,
        remarks: str | None = None,
    ) -> AxiomSystem: ...

    def get_system(self, id: int) -> AxiomSystem: ...
    def get_system_by_name(self, name: str) -> AxiomSystem: ...
    def list_systems(self) -> list[AxiomSystem]: ...

    # ── メンバーシップ ─────────────────────────────────────────────────────────

    def add_to_system(self, axiom_system_id: int, axiom_id: int) -> None: ...
    def remove_from_system(self, axiom_system_id: int, axiom_id: int) -> None: ...
    def list_system_members(self, axiom_system_id: int) -> list[Axiom]: ...
    def is_subset(self, child_system_id: int, parent_system_id: int) -> bool: ...

    # ── Phase 4 用内部メソッド ─────────────────────────────────────────────────

    def _register_definition_derived(
        self,
        name: str,
        formula_id: int,
        definition_id: int,
        remarks: str | None = None,
    ) -> Axiom: ...
```

---

## メソッド仕様

### Axiom 系

#### `register(name, formula_id, remarks) -> Axiom`

| 項目 | 内容 |
|---|---|
| 概要 | primitive 公理を登録する。`origin_kind = 'primitive'`, `definition_id = NULL` で固定 |
| 戻り値 | 登録した `Axiom` モデル |

**バリデーション順序**:

| 条件 | 例外 |
|---|---|
| `formula_id` が存在しない | `NotFoundError("Formula", formula_id)` |
| formula の formula_type が「命題」でない | `ValidationError("axiom formula must be a proposition")` |
| `name` が既存 Axiom と重複 | `ConflictError("Axiom", "name", name)` |

**設計上の注意**: 同じ `formula_id` に対して複数の Axiom を登録することは制約していない (`axiom.md` の論点 1 参照)。同一論理式を異なる origin で登録するケースを許容する。

#### `get(id) -> Axiom`

| 戻り値 | `Axiom` モデル |
|---|---|
| 例外 | `NotFoundError("Axiom", id)` |

#### `get_by_name(name) -> Axiom`

| 戻り値 | `Axiom` モデル |
|---|---|
| 例外 | `NotFoundError("Axiom", name)` |

#### `list_axioms() -> list[Axiom]`

全 Axiom を `id` 昇順で返す。0 件なら空リスト。

---

### AxiomSystem 系

#### `register_system(name, remarks) -> AxiomSystem`

| 項目 | 内容 |
|---|---|
| 概要 | 公理系を登録する (メンバーなし、空の集合として作成) |
| 戻り値 | 登録した `AxiomSystem` モデル |
| 例外 | `ConflictError("AxiomSystem", "name", name)` |

公理系の名前例: `"propositional_classical"`, `"FOL_classical"`, `"ZFC"`, `"PA"`, `"Heyting"`

#### `get_system(id) -> AxiomSystem` / `get_system_by_name(name) -> AxiomSystem`

| 例外 | `NotFoundError("AxiomSystem", id/name)` |
|---|---|

#### `list_systems() -> list[AxiomSystem]`

全 AxiomSystem を `id` 昇順で返す。

---

### メンバーシップ系

#### `add_to_system(axiom_system_id, axiom_id) -> None`

| 項目 | 内容 |
|---|---|
| 概要 | 公理を公理系に追加する |
| 戻り値 | `None` |

**バリデーション**:

| 条件 | 例外 |
|---|---|
| `axiom_system_id` が存在しない | `NotFoundError("AxiomSystem", axiom_system_id)` |
| `axiom_id` が存在しない | `NotFoundError("Axiom", axiom_id)` |
| すでにメンバー | `ConflictError("AxiomSystemMember", "axiom_id", str(axiom_id))` |

#### `remove_from_system(axiom_system_id, axiom_id) -> None`

| 項目 | 内容 |
|---|---|
| 概要 | 公理を公理系から削除する |
| 戻り値 | `None` |
| 例外 | `NotFoundError("AxiomSystem", axiom_system_id)` / `NotFoundError("Axiom", axiom_id)` |

メンバーでない axiom を `remove_from_system` しようとした場合は `NotFoundError` ではなく**静かに無視**する。冪等な操作にすることで「確実に外す」用途を簡潔に書ける。

#### `list_system_members(axiom_system_id) -> list[Axiom]`

| 項目 | 内容 |
|---|---|
| 概要 | 公理系に属する全 Axiom を `axiom.id` 昇順で返す |
| 戻り値 | `list[Axiom]` |
| 例外 | `NotFoundError("AxiomSystem", axiom_system_id)` |

#### `is_subset(child_system_id, parent_system_id) -> bool`

| 項目 | 内容 |
|---|---|
| 概要 | 公理系 `child` のメンバー集合が `parent` のメンバー集合に含まれるか判定する |
| 戻り値 | `True` (X ⊆ Y) / `False` |
| 例外 | `NotFoundError("AxiomSystem", ...)` (どちらかが存在しない場合) |

**実装**: SQL の `EXCEPT` を使った 1 クエリで判定する。

```sql
SELECT NOT EXISTS (
  SELECT axiom_id FROM axiom_system_member WHERE axiom_system_id = :child_id
  EXCEPT
  SELECT axiom_id FROM axiom_system_member WHERE axiom_system_id = :parent_id
)
```

`child_id == parent_id` のときは `True` (空集合の EXCEPT は空になるため、自然に正しく動く)。

---

### `_register_definition_derived(name, formula_id, definition_id, remarks) -> Axiom` (内部)

| 項目 | 内容 |
|---|---|
| 概要 | `origin_kind = 'definition_derived'` で、`definition_id` をセットした状態で Axiom を登録する。`DefinitionService` からのみ呼ぶ |
| 戻り値 | 登録した `Axiom` モデル |

Phase 4 で `DefinitionService.register()` が実行する 5 ステップのうち step 4 がこのメソッドを呼ぶ。呼び出し時点で definition 本体は INSERT 済み (`session.flush()` で ID 確定済み) であり、`definition_id` は最初からセットされる。後付けの `UPDATE` は存在しない (`definition-service.md` の「循環参照の解消」参照)。

バリデーションは `register()` と同じ (formula 存在確認 + 命題確認 + name UNIQUE) に加え、`definition_id` の存在確認を行う。

---

## 使用例

### K 公理・S 公理の登録と公理系への追加

```python
from sqlalchemy.orm import Session
from dem.services.axiom import AxiomService
from dem.services.formula import FormulaService
from dem.types import Token

with Session(engine) as session:
    with session.begin():
        fml_svc = FormulaService(session)
        axm_svc = AxiomService(session)

        # 事前に formula を登録しておく (φ, ψ などの symbol も登録済みとする)
        phi = sym_svc.get_by_name("φ")   # arity=0 命題型自由変数
        psi = sym_svc.get_by_name("ψ")
        imp = sym_svc.get_by_name("→")

        # K 公理: φ → ψ → φ
        k_formula = fml_svc.register([
            Token(symbol_id=imp.id), Token(symbol_id=phi.id),
            Token(symbol_id=imp.id), Token(symbol_id=psi.id), Token(symbol_id=phi.id),
        ])
        k_axiom = axm_svc.register(name="K", formula_id=k_formula.id)

        # S 公理: (φ → ψ → χ) → (φ → ψ) → (φ → χ)
        chi = sym_svc.get_by_name("χ")
        s_formula = fml_svc.register([...])
        s_axiom = axm_svc.register(name="S", formula_id=s_formula.id)

        # 命題論理公理系を作成して K, S を追加
        prop_system = axm_svc.register_system(name="propositional_classical")
        axm_svc.add_to_system(prop_system.id, k_axiom.id)
        axm_svc.add_to_system(prop_system.id, s_axiom.id)
```

### 公理系の包含判定

```python
core      = axm_svc.get_system_by_name("hilbert_core")
classical = axm_svc.get_system_by_name("hilbert_classical")

# hilbert_core が hilbert_classical に含まれるか
assert axm_svc.is_subset(core.id, classical.id) is True

# hilbert_classical は hilbert_peirce を追加で持つため、逆向きには含まれない
assert axm_svc.is_subset(classical.id, core.id) is False
```

---

## 開いている論点

1. **`list_system_members()` の JOIN 方式**。`axiom_system_member` を介して `axiom` を JOIN する 1 クエリか、`axiom_system_member` を取得してから `axiom` を IN クエリで引くか。前者の方がシンプル。
2. **`remove_from_system()` のメンバーでない場合の挙動**。本設計では無視 (冪等) としたが、バグ発見のためにエラーにする選択肢もある。実装時に決定すること。
3. **axiom の削除 API**。Phase 2 では提供しない。将来追加する場合は `proof_step` が参照している axiom を削除できないよう FK 制約か アプリ層チェックが必要。

---

## 履歴

- 2026-04-29: 初版。
- 2026-07-06: 設計レビューを反映。`_register_definition_derived()` に `definition_id` 引数を追加 (definition → axiom の INSERT 順への変更に伴い、後付け UPDATE を廃止)。
