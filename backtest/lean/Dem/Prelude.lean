/-!
# DEM バックテストの prelude

設計: `docs/design/external_verification_backtest_design.md` §4.1

このファイルは**バックテスト全体で唯一の手書き宣言**である。DEM の語彙 (`Dem/Vocabulary.lean`)、
公理 (`Dem/Axioms.lean`)、定理 (`Dem/Theorems/*.lean`) はすべて DB から機械生成される。

ここに宣言を足すことは、バックテストが人間の判断に依存する面積を広げることを意味する。
足す場合は設計書 §4.1 と §10 (信頼境界) を同時に更新すること。
-/

/-- DEM の項型 (`formula_type` の「項」)。中身のない不透明な領域として扱う。

DEM の「命題」型は Lean の `Prop` へ写る。 -/
axiom U : Type

/-- 領域が空でないという規約 (設計 §5.4)。

MP の前件だけに現れて結論から消える自由変数を具体化するときに使う。古典一階述語論理の
標準的な規約だが、**バックテストが追加した仮定**なので、翻訳器は使用箇所をログに出す。 -/
axiom u₀ : U
