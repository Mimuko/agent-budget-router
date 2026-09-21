# 実測コスト比較（MY-180）

`compare_runs.py` は、同一タスクを Cursor → OpenAI API と Codex で完了させた結果を比較する。請求 API や認証情報には接続しない。数値は各ダッシュボード／実行ログから転記し、リポジトリに保存する JSON に API key・会話本文・個人情報を含めない。

## Cursor → OpenAI API

`api_cost_usd`（OpenAI ダッシュボードの確定額）が最優先。確定額がない場合だけ、`usage` とその実行時点の `rates_usd_per_mtok` から計算する。`input_tokens` は cached input を含み、`cached_input_tokens` を別に記録する。OpenAI の Usage API は input / cached input / output を区別して返せる。[公式 API リファレンス](https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage)

```json
{
  "task_id": "my-180-sample-01",
  "execution": "cursor_openai_api",
  "completion": "completed",
  "elapsed_minutes": 18,
  "quality_score": 4.5,
  "api_cost_usd": 0.42,
  "usage": {
    "input_tokens": 64000,
    "cached_input_tokens": 12000,
    "output_tokens": 9000
  }
}
```

`api_cost_usd` がない場合:

```json
{
  "rates_usd_per_mtok": {"input": 4, "cached_input": 0.4, "output": 20}
}
```

料金は変動しうるため、当時の公式モデル料金または実請求を記録する。既定の料金表をコードに埋め込まない。

## Codex

Codexは、プラン内利用枠と追加クレジットを同じ「タスク単価」に混ぜない。プラン内は `billing_mode: "included_plan"` とし、消費クレジット／残枠を観測できる場合だけ `credit_units` として記録する。追加課金分だけが `additional_credit_usd` で Cursor API の実費と直接比較できる。

```json
{
  "task_id": "my-180-sample-01",
  "execution": "codex",
  "completion": "completed",
  "billing_mode": "included_plan",
  "credit_units": 3,
  "elapsed_minutes": 14,
  "quality_score": 4.5
}
```

追加クレジットを使った場合:

```json
{
  "billing_mode": "additional_credit",
  "additional_credit_usd": 0.31
}
```

## ルーティング判定

`CURSOR_API` / `CODEX` は、同じ `task_id`、双方 completed、品質差 0.5 点以内、かつ Cursor の API 実費と Codex の追加クレジット実費がそろう場合だけ返す。それ以外は `MANUAL_REVIEW` または `NO_RECOMMENDATION`。プラン料金を任意にタスクへ配賦して「Codexが無料」と判定しない。

```bash
python scripts/compare_runs.py --cursor examples/measurements/cursor-api.json \
  --codex examples/measurements/codex-included-plan.json
```
