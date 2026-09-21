---
name: agent-budget-router
description: 大きな Agent タスク投入前に、期待コンテキスト・複雑度・Go/Split/Defer・推奨 Lane を見積する FinOps Skill。Repository size ではなく Agent が実際に読む量を推定。親モデル切替や請求保証はしない。
---

# Agent Budget Router

> **Estimate before you agent.**

大きなタスクを Agent に投げる前に、**トークン見積・複雑度・推奨 Lane / モデル・予算リスク**を返す。単なるカウンターではなく、**投入判断（Go / Split / Defer）まで支援する**。実行後は Cursor → OpenAI API と Codex の観測値を比較し、次回の実行先判断も支援する。

正本: [references/estimation-rules.md](references/estimation-rules.md)  
出力形式: [references/output-format.md](references/output-format.md)

## 核心原則

```text
Repository size  ≠  Expected agent context
```

100万行 repo の CSS 1 枚修正と、20 ファイルの Plugin 横断再設計は同じ見積にしない。

## いつ使うか

- 大規模・初回・予算不安があるタスクを Agent に渡す**前**
- mimu-core routing-policy §7 の Lane 委譲**前**（任意）
- 「このまま投げたら焼けるか？」を人間が判断したいとき

## やること / やらないこと

| やる | やらない |
|:-----|:---------|
| Expected agent context のレンジ推定 | 親チャットのモデル自動切替 |
| exploration multiplier 適用 | 請求 API 連携・正確な請求額保証 |
| Go / Split / Defer の判断材料 | mimu-core / Client Plugin の業務判断代行 |
| フェーズ分割と Lane 推奨 | workspace 全量のトークン化 |

## ワークフロー

1. ユーザーのタスク説明を受け取る（必須）
2. 任意: 対象パス・ファイル名のヒントを確認
3. 任意: `python scripts/scan_workspace.py --root <workspace> --hint <path> --json` で関連ファイル候補を取得
4. `python scripts/estimate.py` で見積を実行:

```bash
python <skill>/scripts/estimate.py "タスク説明" \
  --path-hint mimu-core/agents/ \
  --skill-count 5 \
  --scan-json /tmp/scan.json
```

5. [references/output-format.md](references/output-format.md) のテンプレで人間向けレポートを返す
6. Verdict に従い、人間が Go / Split / Defer を決定
7. **GO または Split 後**に routing-policy §7 の Lane 委譲へ進む

## 実測コスト比較（MY-180）

同一タスクを両方で完了させたあと、[references/measurement-schema.md](references/measurement-schema.md) の JSON を記録して比較する。

```bash
python <skill>/scripts/compare_runs.py \
  --cursor <cursor-api-measurement.json> \
  --codex <codex-measurement.json>
```

- Cursor API はダッシュボードの `api_cost_usd` を正本にする。未取得時だけ、その時点の料金と input / cached input / output token から計算する。
- Codexのプラン内利用枠はタスクごとの USD に配賦しない。`included_plan` は残利用枠の判断用、`additional_credit` のみ API 実費と直接比較する。
- 同一 task、双方完了、品質差 0.5 点以内、両方の実費あり、のときだけ `CURSOR_API` または `CODEX` を推薦する。それ以外は人間判断へ戻す。

## Verdict の扱い

| Verdict | Agent の動き |
|:--------|:-------------|
| **GO** | 推奨 Lane で単一投入してよい見込み。スコープを 1 文で固定してから起動 |
| **SPLIT_RECOMMENDED** | フェーズ分割を提案。Planning → analyst-planner、Execution → implementer、Review → cross-reviewer |
| **DEFER** | 投入しない。タスク具体化・人間判断・調査先行を促す |

最終決定は常に人間。

## 3 層との関係

| レイヤー | 担当 | 質問 |
|:---------|:-----|:-----|
| **agent-budget-router** | 投入前 | どれくらい食う？予算内？分割すべき？ |
| **routing-policy §7** | 投入後 | どの Lane / subagent に任せる？ |
| **Skills** | 実行中 | 手順・出力・ガードレール |

## カタログ

- モデル本体: [catalog/models.default.yaml](catalog/models.default.yaml)
- Lane 設定: [catalog/lanes.default.yaml](catalog/lanes.default.yaml)

model / effort / speed は分離。未確認の合成 ID は生成しない。

## 配布形態

| 形態 | 内容 |
|:-----|:-----|
| **Cursor Skill MVP** | 本 SKILL + references + scripts + catalog |
| **OpenAI Skill 互換** | 上記 + [agents/openai.yaml](agents/openai.yaml) |

## 例

- [examples/small-fix.md](examples/small-fix.md) — single-file / GO
- [examples/feature-build.md](examples/feature-build.md) — known area / GO
- [examples/large-agent-task.md](examples/large-agent-task.md) — architecture / SPLIT

完了時は Verdict・complexity・context レンジ・推奨 phases を短く報告する。
