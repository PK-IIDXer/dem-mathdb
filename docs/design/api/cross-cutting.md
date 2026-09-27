# Deus Ex Machina — Python ライブラリ API 横断設計

Python ライブラリとして実装する際に全サービスに共通する設計事項を定める。個別サービスの API 設計書はこのドキュメントを前提として読む。

---

## このドキュメントが決めること

- パッケージ構成
- セッション注入方式
- 例外階層
- 共通型定義 (`Token` など)
- サービスメソッドの命名規則と戻り値の約束
- トランザクション境界の考え方

---

## 設計方針

1. **DB 設計と 1 対 1 の層分けを守る**。言語層 → 推論層 → 定義層の実装順序は Phase 1〜4 に対応する。
2. **SQLAlchemy 2.x typed mappings をドメインモデルとして直接使う**。初版では別途 Pydantic / dataclass の DTO は作らない。
3. **サービス層がロジックを持つ**。models は純粋なマッピング、validation アルゴリズムは services に書く。
4. **セッション管理は呼び出し側の責任**。services は受け取ったセッションで `add()` / クエリを発行するだけで、`commit` / `rollback` しない (例外: `DefinitionService` の複合操作は後述)。

---

## パッケージ構成

```
dem/
├── __init__.py
├── errors.py            # 例外階層 (このドキュメントで定義)
├── types.py             # 純粋 Python 型 (Token など、DB 依存なし)
├── db/
│   ├── __init__.py
│   ├── engine.py        # エンジン生成・SessionLocal ファクトリ
│   └── models/
│       ├── __init__.py
│       ├── language.py  # FormulaType, SymbolType, Symbol, Formula, FormulaToken
│       ├── inference.py # InferenceRule, Axiom, AxiomSystem, AxiomSystemMember
│       ├── theorem.py   # Theorem, TheoremPremise, Proof, ProofStep, 代入3テーブル
│       └── definition.py# Definition, DefinitionFormalParam
└── services/
    ├── __init__.py
    ├── symbol.py        # SymbolService   (Phase 1)
    ├── formula.py       # FormulaService  (Phase 1)
    ├── axiom.py         # AxiomService    (Phase 2)
    ├── theorem.py       # TheoremService  (Phase 2)
    ├── proof.py         # ProofService    (Phase 3)
    └── definition.py    # DefinitionService (Phase 4)
```

`tests/` は `dem/` と同階層に置き、`pytest` + `pytest-postgresql` で各サービスを実 DB に対してテストする。

---

## セッション注入

**コンストラクタ注入**を採用する。

```python
# dem/services/formula.py
from sqlalchemy.orm import Session

class FormulaService:
    def __init__(self, session: Session) -> None:
        self._session = session
```

### 呼び出し側の責任

セッションの作成・`commit`・`rollback` は呼び出し側が担う。

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from dem.services.formula import FormulaService
from dem.types import Token

engine = create_engine(DATABASE_URL)

with Session(engine) as session:
    with session.begin():          # 例外が出れば自動 rollback、正常終了で commit
        svc = FormulaService(session)
        formula = svc.register([Token(symbol_id=1), Token(de_bruijn_index=0)])
```

### DefinitionService の複合操作

`DefinitionService.register()` は Symbol + Formula + Definition + Axiom の 5 ステップを一括で行う。
commit は外部のトランザクションに委ねるが、途中で ID が必要な箇所は `session.flush()` を使う。

```python
with Session(engine) as session:
    with session.begin():
        svc = DefinitionService(session)
        defn = svc.register(kind="logical", ...)
        # 例外が出れば session.begin() が rollback → 全 INSERT が取り消される
```

---

## 例外階層

```python
# dem/errors.py

class DemError(Exception):
    """ライブラリ全体の基底例外。"""


class ValidationError(DemError):
    """入力が論理的・構文的に不正。"""


class FormulaValidationError(ValidationError):
    """formula 構成手続き (8 条件) 違反。"""

    def __init__(self, message: str, position: int | None = None) -> None:
        super().__init__(message)
        self.position = position  # token 列内の 0-indexed 位置 (特定できる場合)


class ProofValidationError(ValidationError):
    """proof_step の検証失敗。"""

    def __init__(self, message: str, step_ord: int | None = None) -> None:
        super().__init__(message)
        self.step_ord = step_ord  # 失敗した step の ord (特定できる場合)


class NotFoundError(DemError):
    """参照先レコードが存在しない。"""

    def __init__(self, entity: str, id: int | str) -> None:
        super().__init__(f"{entity} id={id!r} not found")
        self.entity = entity
        self.id = id


class ConflictError(DemError):
    """UNIQUE 制約に抵触する登録 (formula の重複は除く — 後述)。"""

    def __init__(self, entity: str, field: str, value: str) -> None:
        super().__init__(f"{entity}.{field}={value!r} already exists")
        self.entity = entity
        self.field = field
        self.value = value
```

### formula の重複はエラーではない

`formula` テーブルは `hash` に UNIQUE 制約を持つが、同じ論理式の再登録は **エラーではなく既存レコードを返す**。
これは設計上の意図であり `ConflictError` にはならない。

```python
f1 = formula_svc.register(tokens)
f2 = formula_svc.register(tokens)  # ConflictError ではなく f1 と同一の Formula を返す
assert f1.id == f2.id
```

---

## 共通型定義

### `Token`

`formula_token` の 1 要素を表す純粋 Python 型。DB 依存がないため `dem/types.py` に置く。

```python
# dem/types.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    """
    formula_token の 1 要素。
    symbol_id と de_bruijn_index はどちらか一方のみ指定する。
    """

    symbol_id: int | None = None
    de_bruijn_index: int | None = None

    def __post_init__(self) -> None:
        both_none = self.symbol_id is None and self.de_bruijn_index is None
        both_set  = self.symbol_id is not None and self.de_bruijn_index is not None
        if both_none or both_set:
            raise ValueError(
                "Token requires exactly one of symbol_id or de_bruijn_index"
            )
        if self.de_bruijn_index is not None and self.de_bruijn_index < 0:
            raise ValueError("de_bruijn_index must be >= 0")

    @property
    def is_symbol(self) -> bool:
        return self.symbol_id is not None

    @property
    def is_bound_var(self) -> bool:
        return self.de_bruijn_index is not None
```

`frozen=True` により Token はハッシュ可能で、token 列を `tuple[Token, ...]` として扱うことができる。

### `FormulaTypeName` / `SymbolTypeName` (Enum)

シードデータの名前文字列 (`"項"` / `"命題"`、`"関数記号"` など) をコード中で裸の `str` として比較すると、typo が実行時 (しかも比較が偽になるだけ) まで検出されない。純粋 Python 側では `str` 継承の Enum として扱う。

```python
# dem/types.py
from enum import Enum


class FormulaTypeName(str, Enum):
    TERM = "項"
    PROPOSITION = "命題"


class SymbolTypeName(str, Enum):
    FUNCTION      = "関数記号"
    PREDICATE     = "述語記号"
    LOGICAL       = "論理記号"
    QUANT_PROP    = "命題型量化記号"
    QUANT_TERM    = "項型量化記号"
    FREE_TERM_VAR = "項型自由変数記号"
    FREE_PROP_VAR = "命題型自由変数記号"
```

`str` 継承なので DB から取得した name 文字列との変換が容易 (`SymbolTypeName(row.name)`)。DB 側のシードデータと Enum の値が一致していることは起動時またはテストで検証する。

### `SymbolMeta`

formula の構成手続き検証 (parse アルゴリズム) が必要とする Symbol + SymbolType の情報を束ねた純粋 Python 型。
DB に依存しないため、`validate_tokens()` をテスト時に DB なしで呼べる。

```python
@dataclass(frozen=True)
class SymbolMeta:
    """
    parse アルゴリズムが必要とする Symbol + SymbolType の情報。DB 非依存。
    FormulaService._load_symbol_meta() がバッチ SELECT して生成する
    (name 文字列は Enum に変換される。未知の名前はその時点でエラー)。
    """
    arity: int
    symbol_type_name: SymbolTypeName
    output_formula_type: FormulaTypeName
    input_formula_type: FormulaTypeName | None  # None は「引数を取らない種類」
    is_quantifier: bool
```

### Phase 3 以降の型

代入 (`Substitution`) など Phase 3 で必要になる型は、Phase 3 の API 設計書策定時に `dem/types.py` に追記する。

---

## サービスメソッドの命名規則と戻り値

| prefix | 意味 | 正常戻り値 | 重複・不在時 |
|---|---|---|---|
| `register_` | 新規登録 | 登録済みモデル | formula のみ既存返却、他は `ConflictError` |
| `get_` | 単件取得 | モデル | 存在しなければ `NotFoundError` |
| `list_` | 複数取得 | `list[Model]` | 0 件なら空リスト |
| `validate_` | 検証のみ (副作用なし) | `None` | 失敗時は `ValidationError` 系を raise |

`validate_*` メソッドは DB への書き込みを行わない。たとえば `FormulaService.validate(tokens)` は formula を登録せずに 8 条件チェックだけ行う。

---

## トランザクション境界

| 操作の種類 | トランザクション | 備考 |
|---|---|---|
| 読み取り (`get_*`, `list_*`) | 不要 (autocommit 可) | 呼び出し側の裁量 |
| 単一テーブルへの書き込み | 呼び出し側が `session.begin()` | services は `session.add()` のみ |
| `DefinitionService.register` | 呼び出し側の `session.begin()` に乗る | 内部で `session.flush()` を使い ID を取得 |

ネストしたサービス呼び出し (例: `DefinitionService` が内部で `FormulaService` を使う) は、同一セッションを受け渡すことで 1 トランザクション内に収める。

```python
class DefinitionService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._formula_svc = FormulaService(session)   # 同一セッションを共有
        self._symbol_svc  = SymbolService(session)
        self._axiom_svc   = AxiomService(session)
```

---

## 共通列 (created_at / updated_at)

時間軸ポリシー (INDEX の「時間軸の扱い」) に対応するモデル実装の約束:

- 純明細テーブル (`formula_token`, `theorem_premise`, `proof_step_arg`, `proof_step_subst_*`, `definition_formal_param`) を除く全モデルに `created_at: Mapped[datetime]` を `server_default=func.now()` で定義する。
- 状態が変化する `theorem` / `proof` には `updated_at` を `server_default=func.now(), onupdate=func.now()` で定義する。
- services はこれらの列を明示的に設定しない (DB / ORM のデフォルトに任せる)。

---

## 開いている論点

1. **`session.flush()` vs `session.commit()` の境界を実装で確認する**。`DefinitionService` の 5 ステップは `flush()` で ID を取得しながら進める想定だが、SQLAlchemy の identity map を活用すれば不要な `flush()` を省けるか実装時に判断する。
2. **`types.py` の型を `dem/db/models/` に依存させるか**。現状 `Token` は純粋 Python 型としているが、将来的にモデル間で型を共用したくなった場合の分離境界の見直し。
3. **バルク操作の API**。`formula_token` の一括挿入など、大量データ時のパフォーマンス対策として `session.execute(insert(...).values(...))` を使う場合、service のインターフェースをどう設計するか。

---

## 履歴

- 2026-04-28: 初版。パッケージ構成・セッション注入・例外階層・Token 型・命名規則・トランザクション境界を確定。
- 2026-04-29: `SymbolMeta` 型を追加。FormulaService の pure validate 方針に対応。
- 2026-07-06: 共通列 (created_at / updated_at) のセクションを追加。
- 2026-07-06: `FormulaTypeName` / `SymbolTypeName` の `str` 継承 Enum を追加し、`SymbolMeta` のフィールド型を Enum 化 (裸の日本語文字列比較の廃止)。