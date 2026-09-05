# Calibration（v2）

将来の実測補正運用。v1 では蓄積のみ。推定への反映は Phase 3。

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
