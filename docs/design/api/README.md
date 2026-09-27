# API 設計

`dem/services/` の Python ライブラリ API と、その上に薄く載る `webapi/` の REST API。

まず [`cross-cutting.md`](./cross-cutting.md) を読む。パッケージ構成・セッション注入・
例外階層・共通型 (`Token` / `Substitution`) ・命名規則・トランザクション境界は全サービス
共通で、各サービスの設計書はこれを前提にしている。

---

## サービス一覧

`DemServices` (`dem/api/context.py`) が 1 つの SQLAlchemy セッションに束ねる 7 つ。

| 属性 | クラス | 設計書 | 主な責務 |
| --- | --- | --- | --- |
| `symbols` | `SymbolService` | — | `FormulaType` / `SymbolType` の読み取り、`Symbol` の登録、記法・LaTeX テンプレート、`symbol_role` |
| `formulas` | `FormulaService` | [formula-service.md](./formula-service.md) | token 列の 8 条件検証、hash による重複排除つき登録 |
| `axioms` | `AxiomService` | [axiom-service.md](./axiom-service.md) | 公理の登録、公理系のメンバーシップ、`is_subset`、`list_theorems_provable_in_system` |
| `theorems` | `TheoremService` | [theorem-service.md](./theorem-service.md) | 定理ステートメント (結論 + 順序付き前提) の登録・取得 |
| `proofs` | `ProofService` | [proof-service.md](./proof-service.md) | **カーネル本体**。ステップ追加、`validate()`、`list_used_axioms()`、`is_valid_in_system()` |
| `definitions` | `DefinitionService` | — | 5 種の定義登録 (新 Symbol + 定義由来 axiom のアトミック二段組み) |
| `tags` | `TagService` | — | axiom / theorem / definition へのタグ付け。source provenance に使う |

`DemApi` は `from_url()` / `create_schema()` / `seed_core()` / `initialize_database()` と、
`session()` / `transaction()` のコンテキストマネージャを持つ。`seed_core()` が入れるのは
言語層・推論規則・Hilbert core だけで、コンテンツ層は入らない。

---

## 実装との対応で注意する点

設計書は Phase 1〜4 の実装順に書かれており、その後の変更が本文へ反映されていない箇所がある。
食い違ったら**実装が正**。現在わかっている差分:

- `DefinitionService` は **6 種別**を受ける (`predicate` / `function` / `function_desc` /
  `logical` / `quant_prop` / `quant_term`)。うち **`function_desc` (∃!-backed の記述的関数定義) は
  REST API からは作れない。** `DefinitionCreate.kind` は残る 5 種だけを受け付ける。
  `function_desc` は存在一意性の証明 ID を必須にし、その証明を組み立てる補助は削除済みである
  (`hilbert_core` に ∧ と ∃ が無く ∃! を書けない)。設計は
  `../kernel/descriptive-function-definition.md`。
- `ProofService` は `StepInput` を 5 種ではなく **7 種**受ける
  (`Premise` / `Assumption` / `Axiom` / `Theorem` / `MP` / `Gen` / `ImplicationIntro`)。
  `Assumption` と `ImplicationIntro` は 2026-08-07 の ⇒導入 primitive 化で増えた。
- `ProofService.add_raw_steps()` / `reconstruct_steps()` は設計書に無い後発の API で、
  seed 側が大量ステップを積むための一括経路である。受理条件は `add_step()` と同じ。
- 命題型代入の形式パラメータは任意の項を取れる
  (`../kernel/propositional-schema-term-arguments.md`)。

---

## REST API

`webapi/` は上記サービスをほぼそのまま HTTP へ出す。ルータは
`symbols` / `formulas` / `axioms` / `theorems` / `proofs` / `definitions` / `tags` の 7 本。

**REST 層に固有のロジックは無い。** 検証も公理依存の計算もすべてサービス側で行う。
Swagger UI (`/docs`) が事実上のエンドポイント一覧なので、本フォルダにルータごとの
設計書は置かない。起動手順はリポジトリルートの
[`README.md`](../../../README.md)。

例外は**表示のための読み取り**で、いずれもサービス側に対応物を持たない薄いクエリを
web 層に置いている。`GET /formulas` (一覧。`FormulaService` は設計として一括取得を持たない)
と `GET /proofs/{id}/formulas` (その proof の step 結論式を重複を除いて token 付きで返す) で
ある。後者は閲覧 UI が proof 1 本の描画を 1 リクエストで済ませるためのもので、無いと
distinct な論理式の数だけリクエストが飛ぶ。

同じ理由で `GET /proofs/{id}/direct-dependencies` も置く。その proof の step が直接引く
公理と補題定理 (名前・status と、step が pin した proof id 付き) を返す。定理ページの
依存関係ツリーが補題ごとに `GET /proofs/{id}` と `GET /theorems/{id}` を投げていた分
を 1 本にし、補題の子は展開したときだけ取得する。

`GET /formulas/batch?ids=1,2,3` は指定した論理式を token 付きで返す。重複は除き、
distinct な id は 500 個まで (超えると 422)。存在しない id は結果から省くだけで失敗に
しない。並びは渡した順ではなく id 順 (SQLite と PostgreSQL で行順を揃えるため
`ORDER BY` を明示する。token は `position` 順)。定理ページの文と定理検索の結果カードを
1 本にするためのもので、フロントエンドはこの結果で `['formulas', id]` のキャッシュを
埋め、個別の取得をキャッシュヒットにする (`usePrimeFormulas`)。
`GET /formulas` は従来どおりページング付きの一覧で、こちらは変えていない。

レスポンスは `GZipMiddleware` で圧縮する。token 列は長く反復が多いため、圧縮がよく効く。

日時フィールド (`created_at` / `updated_at`) は DB 方言にかかわらず UTC に正規化し、
ISO 8601 の末尾 `Z` (`2026-09-14T12:24:15.285357Z`) で返す。SQLite のタイムゾーン無し値は
`CURRENT_TIMESTAMP` の意味に従って UTC とみなし、タイムゾーン付き値は UTC へ変換する。
元の値にマイクロ秒が無ければ、出力にも付けない。

---

## 履歴

- 2026-09-16: REST API の日時を DB 方言にかかわらず UTC の `…Z` 形式で返す規約を追加した。
- 2026-08-23: 初版。`cross-cutting.md` にあった索引的な記述をここへ分け、
  実装との既知の差分と REST 層の位置づけを追加した。
- 2026-08-29: `GET /proofs/{id}/formulas` と `GZipMiddleware` を追加し、REST 層に置く
  「表示のための読み取り」の位置づけを書いた。
- 2026-09-15: `GET /proofs/{id}/direct-dependencies` を追加した。
- 2026-09-15: `GET /formulas/batch` を追加した。
