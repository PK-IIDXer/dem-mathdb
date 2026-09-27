# テーブル一覧

`dem/db/models/` が定義する **5 層 30 テーブル**。本書は「どこに何があるか」と
「実装が実際に持っている列・制約」の索引である。各テーブルに関する詳細な設計は、
同梱されているサービス設計書と、公開スナップショットでは省略された `../kernel/` の
対応する設計書に記録されている。

一覧の出所は `dem/db/models/` そのもの。列や CHECK 制約を変えたら本書も直すこと。

---

## 言語層 (8 テーブル)

設計書: `kernel/symbol.md`, `kernel/formula.md`

| テーブル | 役割 | 押さえる制約 |
| --- | --- | --- |
| `namespace` | 記号名の名前空間。`parent_id` で親名前空間を参照する | `name` は UNIQUE |
| `formula_type` | 項 / 命題の enum。2 行だけ | `code` は `term` / `proposition` |
| `symbol_type` | 記号の種類。7 行 (関数・述語・論理・命題型量化・項型量化・項型自由変数・命題型自由変数) | `input_or_zero_arity`: 入力型を持たない種類は arity 0 に限る |
| `symbol` | 個別の記号。名前空間に属し、`usage_count` はその記号を含む相異なる formula 数を保持する | `(namespace_id, name)` UNIQUE、`infix_requires_arity_two`, `precedence_matches_notation_kind` |
| `symbol_alias` | 記号を検索・解決するための別名 | `alias` は UNIQUE。`source` は `builtin` / `user` |
| `symbol_role` | カーネルが役割で引く記号。4 行 (`implication` / `universal_quantifier` / `biconditional` / `equality`) | `known_role` が 4 値を固定。`symbol_id` は UNIQUE |
| `formula` | 論理式そのもの。`hash` UNIQUE で重複排除 | `token_count > 0` |
| `formula_token` | polish notation の token 列 | `exactly_one_kind`: `symbol_id` と `de_bruijn_index` は排他。`(formula_id, position)` UNIQUE |

`symbol_type` の 7 行は「引数に取れる論理式の種類」と「固定 arity」を持つ。
`arity` は `symbol` 側にあり、`symbol_type.fixed_arity` が非 NULL なら一致が要求される
(アプリ層で検証)。

---

## 推論層 (13 テーブル)

設計書: `kernel/inference-rule.md`, `kernel/axiom.md`, `kernel/theorem-proof.md`

| テーブル | 役割 | 押さえる制約 |
| --- | --- | --- |
| `inference_rule` | **MP / Gen / ImpIntro の 3 行のみ** | `known_kind` が 3 kind を固定。`known_tier` が 4 tier を固定。`admissible_requires_elimination_procedure` |
| `axiom` | 公理 (formula へのタグ + 出自) | `origin_definition_consistency`: `definition_derived` なら `definition_id` 必須、`primitive` なら NULL |
| `axiom_system` | 公理系 | — |
| `axiom_system_member` | 公理系のメンバーシップ (多対多) | — |
| `theorem` | 定理または予想 | `status IN ('conjecture', 'proven')` |
| `theorem_premise` | 定理の前提 (順序付き) | `ord >= 0` |
| `proof` | 証明。1 定理に複数登録可 | `status IN ('draft', 'verified', 'rejected')`、`(theorem_id, identity_ordinal)` UNIQUE |
| `proof_identity_sequence` | 定理ごとの次の proof identity ordinal。proof 削除後も単調な割り当てを保つ | `theorem_id` が主キー |
| `proof_step` | 証明ステップ | `known_step_kind` (5 種)、`kind_column_consistency`、`gen_variable_only_for_rule` |
| `proof_step_arg` | 過去ステップへの参照 | `references_prior_step`: `referenced_step_ord < step_ord` |
| `proof_step_subst_term` | 項型自由変数への代入 | — |
| `proof_step_subst_prop` | 命題型自由変数への代入 (本体) | — |
| `proof_step_subst_prop_param` | 命題型代入の形式パラメータ列 | `ord >= 0` |

代入は 3 テーブルに正規化されている。`proof_step_subst_prop` が本体式を、
`proof_step_subst_prop_param` がその lambda 風の形式パラメータを順序付きで持つ。
`proof_step_arg` と代入 3 テーブルはすべて `(proof_id, step_ord)` の複合 FK で
`proof_step` に繋がっており、ステップが消えれば一緒に消える。

**`proof_step.applied_proof_id` は theorem ではなく proof を指す。** これが公理依存の
再帰 CTE が決定的である理由であり、体系の要である (`architecture.md` §3)。

---

## 定義層 (2 テーブル)

設計書: `kernel/definition.md`, `kernel/descriptive-function-definition.md`

| テーブル | 役割 | 押さえる制約 |
| --- | --- | --- |
| `definition` | 新記号の導入。6 種 | `known_kind`: `predicate` / `function` / `logical` / `quant_prop` / `quant_term` / `function_desc`。`function_desc_requires_proof` |
| `definition_formal_param` | 定義の形式パラメータ (順序付き) | `ord >= 0` |

定義の登録は **新 Symbol の登録 + その振る舞いを定める axiom の登録**の二段組み
トランザクションである。`axiom.definition_id` は UNIQUE なので、1 定義に定義由来
axiom はちょうど 1 本。FK は axiom → definition の一方向だけで、INSERT 順は
definition → axiom。

`function_desc` (∃!-backed の記述的関数定義) だけは `existence_uniqueness_proof_id` を
必須とし、`DefinitionService.register()` が登録時に「その proof の結論が、同じ
パラメータ・同じ値変数・同じ本体式の一意存在文であること」を token 単位で照合する。

---

## タグ層 (4 テーブル)

| テーブル | 役割 |
| --- | --- |
| `tag` | タグ本体 |
| `axiom_tag` / `theorem_tag` / `definition_tag` | それぞれへの多対多 |

タグは axiom / theorem / definition の検索と分類に使う汎用 metadata である。

---

## 来歴層 (3 テーブル)

| テーブル | 役割 | 押さえる制約 |
| --- | --- | --- |
| `axiom_record` | 非定義公理について、導入理由・対象理論・出典・レビュー情報を記録する | `axiom_id` が主キー |
| `import_record` | 外部から取り込んだ theorem の出典、元の宣言、変換・検査結果、権利情報を記録する | 同一出典の重複を UNIQUE で禁止。検査結果と `upstream_origin` を既知値に限定 |
| `authoring_provenance` | authored entity の作成経路、使用モデル、入力、承認者を記録する監査 metadata | `(entity_kind, entity_id, created_at)` が複合主キー |

これらは証明データに付随する記録で、モデル定義上、proof validation・公理依存計算・
`theorem.status` の判定には使われない。

---

## DB 制約で表現しきれない整合性

以下はアプリ層 (`ProofService.validate()` ほか) が担保する。設計上の一覧は
`kernel/theorem-proof.md` の該当節にある。

- ステップ結論式が、種別ごとの計算結果 (代入・MP の分解・Gen の抽象化) と一致すること
- `symbol.arity` と `symbol_type.fixed_arity` の整合
- 論理式構成手続き (8 条件) の充足
- verified proof と theorem ステートメントの不変性
- 最終ステップが未解消の `assumption` に依存していないこと

---

## 履歴

- 2026-08-23: 初版。設計索引の全テーブル一覧を実装から取り直した。
- 2026-09-27: `Base.metadata.tables` に合わせて 5 層 30 テーブルへ更新した。
