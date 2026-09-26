# Calibration（v2）

将来の実測補正運用。v1 では蓄積のみ。推定への反映は Phase 3。MY-180 の経路別コスト比較は [measurement-schema.md](measurement-schema.md) を使い、ここには context の補正値だけを置く。

## ローカル蓄積

```text
~/.agent-budget-router/calibration.jsonl
```

1 行 1 タスク（JSONL）:

```json
{
  "timestamp": "2026-09-05T12:00:00Z",
  "predicted_context_min": 180000,
  "predicted_context_max": 260000,
  "actual_context": 310000,
  "task_type": "architecture / unknown repo",
  "workspace_fingerprint": "agent-plugins",
  "ratio": 1.26
}
```

## 補正の使い方（Phase 3）

N 件（目安 10+）蓄積後、タスク種別ごとの平均 ratio をレポートに追記:

> 「この workspace では architecture タスクの context 推定は実測で ×1.26 傾向」

## 原則

- **個人ローカル**が既定
- 共有は opt-in（チームで calibration を共有する場合は別途合意）
- 実測値は請求 API ではなく、ユーザーが観測した usage を手入力でよい（v2）
- Cursor API と Codex の USD 比較は、Codexが追加クレジットを使った実行だけで厳密に行う。プラン内枠は直接費としてCodex優位の判断に使えるが、恣意的な固定費配賦はしない
- 日常運用の履歴は `abr.py record` が `~/.agent-budget-router/runs.jsonl` に保存する。主観的な5点評価ではなく、completion / acceptance / tests / lint / build / revisions を優先する
- `abr.py route` / `finish` の前後スナップショット差分は、並行実行なしを確認できた場合だけ `HIGH` attribution として次回の allowance impact 推定に使う。並行実行あり・不明はアカウント全体の参考値として保持する
- allowance impact は単一値ではなくレンジで表示する。高Confidenceの同種履歴が0件ならタスク種別prior（LOW）、3件以上でMEDIUM、6件以上でHIGHとする
