# Deus Ex Machina — FormulaService API 設計 (Phase 1)

Phase 1 で実装する `FormulaService` の API 仕様。formula トークン列のバリデーション・登録・取得を担う。

横断設計 (`cross-cutting.md`) と `symbol-service.md` を前提として読むこと。

---

## 責務

- formula トークン列の構成手続き検証 (8 条件)
- formula の登録 (hash 計算 + 重複排除)
- formula / formula_token の取得

---

## 構造の概要: pure 関数とサービス層の分離

**設計方針**: N+1 クエリを避けること、および検証ロジックを DB なしでテスト可能にすることを目的として、検証アルゴリズムをモジュールレベルの **pure 関数** として実装する。

```
呼び出し元
  │
  ▼
FormulaService.validate(tokens)
  │  1. _load_symbol_meta(tokens) — symbol_id を一括 SELECT (1 クエリ)
  │  2. validate_tokens(tokens, meta) — pure 関数を呼ぶ (DB アクセスなし)
  │
FormulaService.register(tokens, remarks)
  │  1. _load_symbol_meta(tokens) — 同上 (1 クエリ)
  │  2. validate_tokens(tokens, meta) — pure 関数 (formula_type も取得)
  │  3. hash 計算 → 重複チェック → INSERT
```

`validate_tokens()` はモジュールレベル関数として公開し、テスト時に `dict[int, SymbolMeta]` を直接渡せる。

---

## モジュールレベル純粋関数

```python
# dem/services/formula.py (クラス定義の外)
from dem.types import Token, SymbolMeta, FormulaTypeName
from dem.errors import FormulaValidationError


def validate_tokens(
    tokens: list[Token],
    symbol_meta: dict[int, SymbolMeta],
) -> FormulaTypeName:
    """
    8 条件の構成手続き検証。DB アクセスをしない pure 関数。

    Returns:
        最外 token の出力型 (FormulaTypeName.TERM / FormulaTypeName.PROPOSITION)

    Raises:
        FormulaValidationError: 検証失敗時
        KeyError: tokens に含まれる symbol_id が symbol_meta に存在しないとき
                  (呼び出し元が _load_symbol_meta() を正しく呼んでいれば発生しない)
    """
    ...
```

`validate_tokens()` の戻り値は `FormulaTypeName.TERM` または `FormulaTypeName.PROPOSITION` (= 論理式全体の種類)。
`FormulaService.validate()` はこれを捨てる。`register()` は `formula_type_id` の特定に使う。

---

## クラスシグネチャ

```python
# dem/services/formula.py
from sqlalchemy.orm import Session
from dem.db.models.language import Formula, FormulaToken
from dem.types import Token, SymbolMeta


class FormulaService:
    def __init__(self, session: Session) -> None: ...

    # ── Public API ────────────────────────────────────────────────────────────

    def validate(self, tokens: list[Token]) -> None: ...

    def register(
        self,
        tokens: list[Token],
        remarks: str | None = None,
    ) -> Formula: ...

    def get(self, id: int) -> Formula: ...
    def get_by_hash(self, hash: str) -> Formula: ...
    def get_tokens(self, formula_id: int) -> list[FormulaToken]: ...

    # ── 具象構文 (DSS) との往復 (UX Phase 1.1 / 1.3) ──────────────────────────

    def parse_text(
        self, text: str, context: dict[str, int] | None = None
    ) -> tuple[list[Token], int | None]: ...

    def print_text(self, tokens: list[Token]) -> str: ...

    def surface_symbol_table(self) -> "demlang.SymbolTable": ...

    # ── 内部ヘルパー (実装時のみ参照) ─────────────────────────────────────────

    def _load_symbol_meta(self, tokens: list[Token]) -> dict[int, SymbolMeta]: ...
```

### 具象構文との往復 (UX Phase 1、2026-09-08)

`demlang/` は DB を知らない純粋パッケージであり、`FormulaService` がその境界になる。

| メソッド | 内容 |
|---|---|
| `surface_symbol_table()` | 記号 (name / arity / symbol_type / notation_kind / precedence) と別名を読み、`demlang.SymbolTable` を組んで返す。パーサ・プリンタが必要とする情報はこれで全部である |
| `parse_text(text, context)` | convenience モードで解析し、`validate_tokens` を通してから `(tokens, 既存 formula の id または None)` を返す。**登録はしない** ([`../ux/phase1.md`](../omitted-history.md) §1.3)。`context` は「宣言名 → symbol_id」の局所対応表 |
| `print_text(tokens)` | 編集形 (DSS) の文字列を返す。表示形の LaTeX は別物であり、`renderLatex` が引き続き担当する |

構文エラーは `FormulaValidationError(code="formula.syntax_error")` になり、`details.position` に文字位置、期待型が分かる場合は `details.expected_type` を載せる。補完のランキング (Phase 1.6) はこの `expected_type` を使う。

`parse` / `print` は純粋な読み取りである。長い式とcontext辞書をURLへ載せないためPOSTを維持し、`DEM_READ_ONLY`でもこの2 pathだけmiddlewareの許可リストを通る。`suggest`などの書き込みPOSTは許可しない ([`../ux/phase1.md`](../omitted-history.md) §5.3 D8)。

---

## メソッド仕様

### `validate(tokens) -> None`

| 項目 | 内容 |
|---|---|
| 概要 | token 列の構成手続き検証。DB 書き込みなし |
| 戻り値 | `None` |
| 例外 | `FormulaValidationError(message, position)` |

**処理の流れ**:

```
1. _load_symbol_meta(tokens) で symbol_id を一括 SELECT (1 クエリ)
2. validate_tokens(tokens, meta) を呼ぶ (pure — DB アクセスなし)
3. 例外があれば FormulaValidationError をそのまま伝播
```

DB へのアクセスは 1 クエリのみ (token 数に依らず N+1 にならない)。

---

### `register(tokens, remarks) -> Formula`

| 項目 | 内容 |
|---|---|
| 概要 | token 列を検証し、新しい formula として登録する |
| 戻り値 | 登録した (または既存の) `Formula` モデル |
| 例外 | `FormulaValidationError` (検証失敗時) |
| 重複時 | エラーにせず **既存の Formula を返す** |

**処理の流れ**:

```
1. _load_symbol_meta(tokens) で symbol_id を一括 SELECT (1 クエリ)
2. validate_tokens(tokens, meta) を呼び、FormulaTypeName (TERM / PROPOSITION) を得る
3. compute_hash(tokens) で SHA256 ハッシュを計算
4. SELECT formula WHERE hash = ? → 存在すれば既存レコードを返して終了
5. formula_type_id を FormulaTypeName から引く (FormulaType は初期 2 件なのでキャッシュ可)
6. INSERT formula (formula_type_id, hash, token_count=len(tokens), remarks)
7. INSERT formula_token × N 件 (一括 INSERT)
8. token列に現れた各記号の `usage_count` 増分をtransaction内で蓄積する。同じ記号が複数回現れても1回だけ増やす
9. Formula モデルを返す
```

step 1 の `_load_symbol_meta()`、step 7 の一括INSERTにより、DBクエリ数はtoken数に依らずO(1)に保たれる。step 8の増分は記号ごとに合算し、一覧取得時またはcommit直前に1回のexecutemanyで反映するため、大量seedでもformulaごとのUPDATEを発行しない。既存formulaを返す場合は集計値を変更しない。

---

### `get(id) -> Formula`

| 項目 | 内容 |
|---|---|
| 戻り値 | `Formula` モデル |
| 例外 | `NotFoundError("Formula", id)` |

---

### `get_by_hash(hash) -> Formula`

| 項目 | 内容 |
|---|---|
| 戻り値 | `Formula` モデル |
| 例外 | `NotFoundError("Formula", hash)` |

hash の生成方法は後述の「Hash 計算仕様」を参照。

---

### `get_tokens(formula_id) -> list[FormulaToken]`

| 項目 | 内容 |
|---|---|
| 概要 | formula に属する全 token を position 昇順で返す |
| 戻り値 | `list[FormulaToken]` (position 0 始まり昇順) |
| 例外 | `NotFoundError("Formula", formula_id)` |

**実装上の注意**: `Formula` モデルに `tokens` リレーションを定義しても `lazy="raise"` を指定し、遅延ロードを禁止する。token 列が必要な場合は必ずこのメソッドを呼ぶ。これにより呼び出し元で N+1 が発生しない。

```python
# Formula モデル側の設定イメージ
tokens: Mapped[list["FormulaToken"]] = relationship(
    order_by="FormulaToken.position",
    lazy="raise",   # 明示的な get_tokens() 呼び出しを強制
)
```

---

### `_load_symbol_meta(tokens) -> dict[int, SymbolMeta]` (内部)

| 項目 | 内容 |
|---|---|
| 概要 | tokens に含まれる全 symbol_id を一括 SELECT し、`SymbolMeta` の辞書を返す |
| 戻り値 | `{symbol_id: SymbolMeta, ...}` |
| 例外 | `NotFoundError("Symbol", symbol_id)` (tokens 内に存在しない symbol_id がある場合) |

**処理の流れ**:

```
1. tokens から symbol_id を重複排除して抽出 (de Bruijn 参照は除外)
2. SELECT symbol.id, symbol.arity,
          symbol_type.name, symbol_type.output_formula_type_id, formula_type_A.name AS output_name,
          symbol_type.input_formula_type_id,  formula_type_B.name AS input_name,
          symbol_type.is_quantifier
   FROM symbol
   JOIN symbol_type ON symbol.symbol_type_id = symbol_type.id
   JOIN formula_type formula_type_A ON symbol_type.output_formula_type_id = formula_type_A.id
   LEFT JOIN formula_type formula_type_B ON symbol_type.input_formula_type_id = formula_type_B.id
   WHERE symbol.id IN (...)
3. 取得できなかった symbol_id があれば NotFoundError
4. dict[int, SymbolMeta] に変換して返す (name 文字列は SymbolTypeName / FormulaTypeName の Enum に変換。未知の名前はこの時点でエラー)
```

---

## 8 条件の構成手続き検証 (validate_tokens の仕様)

`formula.md` の Validation アルゴリズムを実装する。ただし **第 2 段 (命題型自由変数の引数列一致チェック) は実装しない**。`theorem-proof.md` の「補助修正」で撤廃されているため。

### parse の動作

token 列を position 0 から読み進めるスタック型再帰下降パーサ。

```
_parse(tokens, pos, scope_depth, symbol_meta) -> (next_pos, output_formula_type)
  raises FormulaValidationError(message, position=pos)
```

| token の種類 | 成立条件 | 出力型 |
|---|---|---|
| de Bruijn 参照 `k` | `k < scope_depth` | 項 |
| 項型自由変数記号 (arity 0) | なし | 項 |
| 関数記号 (arity n) | 続く n 個が項 | 項 |
| 述語記号 (arity n) | 続く n 個が項 | 命題 |
| 論理記号 (arity n) | 続く n 個が命題 | 命題 |
| 命題型量化記号 | 続く 1 個が命題 (scope_depth + 1 で parse) | 命題 |
| 項型量化記号 | 続く 1 個が命題 (scope_depth + 1 で parse) | 項 |
| 命題型自由変数 (arity n) | 続く n 個が項（各項を完全な部分木として parse） | 命題 |

`validate_tokens()` は `_parse(tokens, pos=0, scope_depth=0, symbol_meta)` を呼び、終了後に `next_pos == len(tokens)` を確認する。

### FormulaValidationError で報告すべき内容

| エラーケース | message 例 | position |
|---|---|---|
| token 列が空 | `"empty token list"` | `None` |
| de Bruijn index が scope 外 | `"unbound de Bruijn index 2 (scope depth 1)"` | 当該位置 |
| 型不一致 | `"expected 項 but got 命題 at position 3"` | 3 |
| arity 不足 (予期せず終端) | `"unexpected end of tokens"` | `None` |
| 余剰 token | `"trailing tokens at position 5"` | 5 |
| 命題型自由変数の引数が項以外 | `"expected 項 but got 命題 at position 3"` | 当該位置 |

---

## Hash 計算仕様

### canonical_form

```
canonical_form(tokens: list[Token]) -> str:
  parts = []
  for token in tokens:
    if token.is_symbol:
      parts.append(f"S{token.symbol_id};")
    else:
      parts.append(f"B{token.de_bruijn_index};")
  return "".join(parts)
```

**例**: `[Token(symbol_id=5), Token(de_bruijn_index=0), Token(symbol_id=3)]`
→ `"S5;B0;S3;"`

### hash

```python
import hashlib

def compute_hash(tokens: list[Token]) -> str:
    form = canonical_form(tokens)
    return hashlib.sha256(form.encode()).hexdigest()
```

locally nameless 表現により $\forall x. P(x)$ と $\forall y. P(y)$ は同一 token 列になり、同一ハッシュになる。

---

## 使用例

### 基本: $\varphi \to \varphi$ の登録

```python
from sqlalchemy.orm import Session
from dem.services.symbol import SymbolService
from dem.services.formula import FormulaService
from dem.types import Token

with Session(engine) as session:
    with session.begin():
        sym_svc = SymbolService(session)
        fml_svc = FormulaService(session)

        implies = sym_svc.get_by_name("→")
        phi     = sym_svc.get_by_name("φ")   # arity=0 の命題型自由変数

        # Polish notation: → φ φ
        tokens = [
            Token(symbol_id=implies.id),
            Token(symbol_id=phi.id),
            Token(symbol_id=phi.id),
        ]

        formula = fml_svc.register(tokens, remarks="φ→φ")
        # 内部で 1 クエリ (symbol_meta 取得) + 重複確認 + INSERT
```

### 検証のみ (登録しない)

```python
from dem.errors import FormulaValidationError

try:
    fml_svc.validate(tokens)
    print("well-formed")
except FormulaValidationError as e:
    print(f"invalid at position {e.position}: {e}")
```

### pure 関数を直接使う (DB なしのテスト用)

```python
from dem.services.formula import validate_tokens
from dem.types import Token, SymbolMeta, FormulaTypeName, SymbolTypeName

# テスト用のスタブ symbol_meta を手動構築
symbol_meta = {
    1: SymbolMeta(arity=2, symbol_type_name=SymbolTypeName.LOGICAL,
                  output_formula_type=FormulaTypeName.PROPOSITION,
                  input_formula_type=FormulaTypeName.PROPOSITION,
                  is_quantifier=False),
    2: SymbolMeta(arity=0, symbol_type_name=SymbolTypeName.FREE_PROP_VAR,
                  output_formula_type=FormulaTypeName.PROPOSITION,
                  input_formula_type=FormulaTypeName.TERM,
                  is_quantifier=False),
}

# → φ φ  (Polish notation)
tokens = [Token(symbol_id=1), Token(symbol_id=2), Token(symbol_id=2)]
formula_type = validate_tokens(tokens, symbol_meta)
assert formula_type is FormulaTypeName.PROPOSITION
```

### 同一式の重複登録

```python
f1 = fml_svc.register(tokens)
f2 = fml_svc.register(tokens)   # 同じ tokens → 既存レコードが返る
assert f1.id == f2.id
```

### token 列の取得

```python
formula = fml_svc.get(formula_id=42)
# formula.tokens にアクセスすると lazy="raise" で例外 → 必ず get_tokens() を使う
tokens_from_db = fml_svc.get_tokens(formula.id)
```

---

## 開いている論点

1. **formula_token の一括 INSERT 方法**。`session.add_all()` は typed mappings と相性が良いが、数百 token を超える場合は `session.execute(insert(FormulaToken).values([...]))` の方が高速。実装時にベンチマークして判断。
2. **`FormulaType` のキャッシュ**。`register()` は最終的に formula_type_id が必要だが、FormulaType は 2 件のシードデータなので初期化時に `SymbolService` 経由で取得してインスタンス変数にキャッシュするか、毎回 SELECT するか。
3. **hash の列型**。SHA256 hexdigest は常に 64 文字。PostgreSQL で `CHAR(64)` にするとインデックス効率が上がる可能性があるが、`TEXT` + UNIQUE インデックスで十分か実装時に確認。

---

## 履歴

- 2026-04-28: 初版。
- 2026-04-29: pure 関数 `validate_tokens()` の導入と `_load_symbol_meta()` による一括 SELECT を明記。
  `get_tokens()` に `lazy="raise"` の方針を追加。
- 2026-07-06: 軽微指摘を反映。`validate_tokens()` の戻り値と `SymbolMeta` を `FormulaTypeName` / `SymbolTypeName` の Enum に変更 (`cross-cutting.md`)。`register()` の INSERT に `token_count` を追加 (`formula.md` の非正規化列)。
- 2026-09-08: UX Phase 1 を反映。`demlang/` との境界となる `parse_text` / `print_text` / `surface_symbol_table` を追加した。
