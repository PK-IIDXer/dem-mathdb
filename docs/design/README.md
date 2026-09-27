# Deus Ex Machina — 設計ドキュメント

数学定理データベース「Deus Ex Machina」の設計書。プロジェクトの動機と哲学は
リポジトリルートの [`README.md`](../../README.md)、AI エージェント向けの作業規約は
[`AGENTS.md`](../../AGENTS.md) にある。本フォルダはその哲学を、実装されている RDB
スキーマと証明カーネルとして記述する。

**設計書は実装に従う。** 食い違いを見つけたら実装を正として設計書を直すこと。

---

## はじめに読む 2 冊

| | |
| --- | --- |
| [`overview/current-state.md`](./overview/current-state.md) | いま DB に何がどれだけ入っているか。公開 seed の内容と信頼境界の現在地 |
| [`overview/schema.md`](./overview/schema.md) | 5 層 30 テーブルの索引。どのテーブルがどの役割を持つか |

---

## フォルダ構成

```text
docs/design/
  overview/   全体像・現在地・共通方針       ── 最初に読む
  api/        Python サービス API と REST 層
  ops/        seed・テスト運用と外部検証
```

---

## overview — 全体像

| ドキュメント | 内容 |
| --- | --- |
| [schema.md](./overview/schema.md) | 全 30 テーブルと押さえるべき CHECK 制約 |
| [current-state.md](./overview/current-state.md) | 実測値。公開 seed の内容、公理系一覧、信頼境界の現在地 |
| [cross-cutting-topics.md](./overview/cross-cutting-topics.md) | 設計書をまたぐ論点。Leibniz 公理問題、proof pinning と公理系、一様代入の健全性など |

---

## api — サービス層

[api/README.md](./api/README.md) がサービス一覧と実装との既知の差分を持つ。
横断設計 [cross-cutting.md](./api/cross-cutting.md) を先に読み、一覧 API の規約は
[pagination.md](./api/pagination.md) を参照する。

個別: [formula](./api/formula-service.md) /
[axiom](./api/axiom-service.md) /
[theorem](./api/theorem-service.md) /
[proof](./api/proof-service.md)

---

## ops — 運用

| ドキュメント | 内容 |
| --- | --- |
| [seed-and-test-performance.md](./ops/seed-and-test-performance.md) | A-only seed をテストごとの分離 DB に構築する方針と、seed 変更時の検証手順 |
| [external-verification-backtest.md](./ops/external-verification-backtest.md) | DEM の検証コードを一切使わず Lean 4 で再検査するバックテスト。DEM の主張を反証可能にする装置 |
| [workspace-schema-upgrade.md](./ops/workspace-schema-upgrade.md) | workspace DB のスキーマ更新手順 |

---

## 同梱されない資料

[omitted-history.md](./omitted-history.md) は、公開スナップショットに含まれない過去の実験、
将来作業のメモ、内部運用資料について説明する。

---

## 履歴

- 2026-08-23: `INDEX.md` を廃し、本 README とフォルダ分割へ再編した。
- 2026-09-27: 公開スナップショットの実在ファイルと 30 テーブルの実装に索引を合わせた。
