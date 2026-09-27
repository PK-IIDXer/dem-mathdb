# 横断トピック

複数の設計書にまたがるため、どれか 1 冊を読んだだけでは掴めない論点。設計書を読む前でも
後でもよいが、実装に手を入れる前には一度目を通しておくこと。

---

理解のために知っておくべき横断トピック。

## Leibniz 公理問題 (formula → theorem_proof)

`formula.md` の「命題型自由変数の引数列一致制約」は Hilbert 流では撤廃される。代わりに代入操作が「lambda 風」(formal parameters 付き) に拡張される。詳細は `theorem-proof.md` の「補助修正」セクション。

## NK → Hilbert 移行表 (inference_rule)

NK 風の推論規則がどう Hilbert の公理に移されるかの対応表は `inference-rule.md` にある。これは axiom 設計の前提になる。

## axiom の `definition_id` FK 後付け (axiom → definition)

`axiom.md` で `definition_id` 列を NULL 許容で確保しておき、`definition.md` の Phase 4 マイグレーションで FK 制約と整合性 CHECK を追加する。FK は axiom → definition の**一方向のみ** (definition 側は axiom への FK を持たない)。登録トランザクションは definition → axiom の順で INSERT するため、制約はすべて即時評価でよい (PostgreSQL の CHECK は DEFERRABLE 化できないため、旧・双方向 FK + 後付け UPDATE 方式は成立しなかった)。

## proof pinning と axiom_system の関係 (axiom ↔ theorem_proof)

専用リンクテーブルを持たない。proof_step の `'theorem'` 種別は特定の検証済み proof を pin する (`applied_proof_id`) ため、pin された proof 連鎖を再帰 CTE で辿れば使用 axiom 集合が一意に定まる。それを axiom_system のメンバーと比較する SQL クエリで判定する (`axiom.md`)。API は `ProofService.list_used_axioms` / `is_valid_in_system`。これは README の「公理系を入れ替えて影響範囲をトレースする」中核機能の実装方法。なお `theorem.status = 'proven'` は「検証済み proof の存在」のみを意味し、公理系相対ではない。

## 正準 definition の breaking content migration

通常の定義修正は新しい definition で表現する。正準 seed corpus 自体を意図して改訂する場合は、
既存 DB の definition axiom や verified proof を UPDATE せず、formula mismatch で fail closed にし、
新 DB 世代を全再seedする。一般方針は
`predicate-encapsulation.md` §4.5、圏定義への具体的適用は
同文書 §9.7〜§9.10を参照する。

## 特別な記号の役割解決 (symbol → 全域)

MP の `→`、Gen の `∀`、定義機構の `↔` / `=` は名前ではなく `symbol.md` の `symbol_role` テーブルで特定する。**`→` は現在 primitive である** (2026-08-12 の言語 seed 見直しで、`¬φ∨ψ` による定義由来 symbol をやめた)。定義由来にすると、その定義由来 axiom が公理系のメンバーシップに関わらず任意の proof から引用でき、`hilbert_k` / `hilbert_s` だけから排中律が導けてしまうためである。`∧` と `∃` も同じ理由で primitive のまま。`↔` はこの機構の前提として **primitive 必須** (定義で導入すると、定義式自体が ↔ を要求して自己言及になる)。

## 一様代入の健全性 (theorem_proof → 全域)

`'theorem'` ステップが引用先証明の Gen 側条件を σ 適用後に再検査しなくてよい根拠 (locally nameless により変数捕獲が構造的に不可能で、Metamath の distinct variable condition に相当する制約が表現側で消えている) は、`theorem-proof.md` の「『theorem』適用の健全性」に明文化されている。このメタ定理は `apply_substitution_pure` / `abstract_and_quantify_pure` の shifting の正しさを前提とするため、**両関数のテストには捕獲防止のケースを必ず含める** (実装時の必須事項)。

命題型自由変数の実引数を一般項へ広げる際の、項部分木境界、実引数内部の再帰的prop pass、
置換本体を再走査しない同時代入規則、複合項全体へのde Bruijn shiftは、
`propositional-schema-term-arguments.md` に定める。

## 自然推論の side condition (theorem_proof → inference_rule)

自然推論の `∀` 導入と `∃` 除去は side condition を持つため、ordinary theorem として同じ扱いにはできない。`∀` 導入は本質的に Gen であり、結論の構築に abstraction が要る。`∃` 除去は `∃φ → ∀(φ→ψ) → ψ` を verified theorem として置き、`ψ` を arity 0 の命題型自由変数にすることで eigenvariable 条件が表現上保たれる。

公開 seed は `Gen` と `ImpIntro` の検証条件を直接テストし、追加の数学 content は同梱しない。

## 外部検証と信頼境界 (全域 → external_verification_backtest)

[`external-verification-backtest.md`](../ops/external-verification-backtest.md) は他の設計書と向きが逆で、**DEM の実装を信頼せずに DB だけを読む**立場から全域に触れる。そのため次の 3 点で他の設計書と結び付く。

- `symbol_role` (`symbol.md`) は、バックテストが `→` と `∀` を同定する唯一の手掛かりである。この 2 つ以外の記号は `symbol_type` と `arity` だけから不透明定数として機械生成されるので、**バックテストが人間の判断に依存するのは `symbol_role` の 2 行の解釈だけ**になっている。`symbol_role` の意味を変える改修はバックテストの信頼境界を直接動かす。
- 「一様代入の健全性」(`theorem-proof.md`) は、バックテストでは Lean の多相定理の適用として自動的に成立する。逆に言えば、このメタ定理が破れていれば Lean 側で型エラーとして現れる。
- ImpIntro の Tier 2 許容性 (`trust-boundary.md` §9) は、バックテストでは `expand_implication_intro()` を経由せず λ 抽象として直接検査される。除去手続きの正しさに依存しない第 2 の確認経路になる。

---

## 履歴

- 2026-08-23: 初版。設計索引の「設計書間の主な相互参照」節を移した。
- 2026-08-25: 正準 definition の breaking content migration を追加。既存 DB を上書きせず、
  formula mismatch と全再seedで verified corpus を世代交代する方針を記録した。
