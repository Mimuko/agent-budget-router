# Estimation rules（正本）

Agent Budget Router の推定ロジック正本。`scripts/estimate.py` は本ファイルに従う。

## 核心原則

```text
Repository size  ≠  Expected agent context
```

- 100万行 repo でも CSS 1 枚修正なら、Agent が読むのはごく一部
- 20 ファイルしかなくても「全仕様照合 + Plugin 横断再設計」は大量に読み直す

v1 は **workspace 全体のトークン数**ではなく、**Agent が実際に読む可能性のある量**を推定する。

## 推定式

```text
Estimated Context
  = Task baseline
  + Expected relevant files
  + Instruction / Skill overhead
  + Re-read / exploration factor
```

| 項 | 内容 | v1 既定レンジ（tokens） |
|:---|:-----|:------------------------|
| **Task baseline** | タスク説明・会話履歴・システム指示の固定分 | 3,000 – 12,000 |
| **Expected relevant files** | タスク種別とパスヒントから推定する読込対象 | パターン依存（下表） |
| **Instruction / Skill overhead** | 有効な Rules / Skills / Plugin 参照の追加分 | 2,000 – 15,000 / skill |
| **Re-read / exploration factor** | 探索→実装→再確認→テスト失敗→再読み の乗数 | パターン依存（下表） |

**Re-read / exploration factor** が、高級モデル全焼の典型原因（探索・subagent・試行錯誤のループ）。

## Exploration multiplier

| パターン | Multiplier | 典型例 |
|:---------|:-----------|:-------|
| `single-file edit` | ×1.1 – 1.3 | CSS 1 ファイル、typo 修正 |
| `known feature area` | ×1.3 – 1.6 | 既知モジュールへの機能追加 |
| `cross-cutting change` | ×1.5 – 2.0 | 複数ディレクトリ・共通ポリシー変更 |
| `architecture / unknown repo` | ×1.8 – 3.0 | 初回調査、Plugin 横断再設計、大規模 Agent タスク |

レポートには `Exploration factor: ×1.8–2.2 (architecture / cross-cutting)` のように **根拠ラベル付き**で出す。

### Expected relevant files（パターン別）

| パターン | ファイル数見込み | トークン見込み（読込前） |
|:---------|:-----------------|:-------------------------|
| `single-file edit` | 1 – 3 | 2,000 – 8,000 |
| `known feature area` | 3 – 12 | 8,000 – 40,000 |
| `cross-cutting change` | 8 – 25 | 25,000 – 80,000 |
| `architecture / unknown repo` | 15 – 60+ | 50,000 – 200,000+ |

`scan_workspace.py` の結果がある場合、上記を実測候補で上書き・絞り込みする（Phase 2 で精緻化）。

## 複雑度スコア

タスク説明から加点し、LOW / MEDIUM / HIGH / CRITICAL にマップする。

| 信号 | 加点 |
|:-----|:-----|
| 「全体」「横断」「初回調査」「要件定義」「Plugin 実装」「アーキテクチャ」「再設計」 | +2 |
| 触るファイル見込み 10+（明示 or 推定） | +2 |
| 新規アーキ / 複数システム / 複数 repo | +2 |
| 1 ファイル修正 / typo / CSS 1 枚 / 単一パス明示 | −2 |
| 明確な受け入れ条件・スコープ限定 | −1 |

| スコア | 複雑度 |
|:-------|:-------|
| ≤ 0 | LOW |
| 1 – 2 | MEDIUM |
| 3 – 4 | HIGH |
| ≥ 5 | CRITICAL |

複雑度は exploration パターン推定と Verdict に接続する。

## Generation 見積

| 複雑度 | Generation（tokens） |
|:-------|:---------------------|
| LOW | 2,000 – 8,000 |
| MEDIUM | 8,000 – 25,000 |
| HIGH | 20,000 – 60,000 |
| CRITICAL | 40,000 – 120,000 |

フェーズ分割（Planning + Execution + Review）時は ×1.5 – 2.0 の係数をレポートに注記。

## Agent overhead ラベル

| 条件 | ラベル |
|:-----|:-------|
| exploration ≥ cross-cutting | HIGH（explore / subagent / re-read 想定） |
| exploration = known feature area | MEDIUM |
| exploration = single-file edit | LOW |

## Verdict 定義

| Verdict | 条件（v1 ヒューリスティック） |
|:--------|:------------------------------|
| **GO** | LOW または MEDIUM。context 上限 80k 未満見込み。単一 Lane で投入可 |
| **SPLIT_RECOMMENDED** | HIGH または context 80k+。フェーズ分割またはスコープ縮小を推奨 |
| **DEFER** | CRITICAL かつ情報不足。または予算制約フラグ + HIGH 以上 |

最終決定は常に人間。

## Confidence

| 条件 | Confidence |
|:-----|:-----------|
| タスク文のみ | LOW |
| パスヒントあり | MEDIUM |
| scan_workspace 結果あり | MEDIUM – HIGH |
| パスヒント + scan 一致 | HIGH |

repo 総行数だけでは Confidence を上げない。

## 未登録モデル

カタログにないモデルは推定に使わず、「未登録 — catalog を更新してください」と出す。
