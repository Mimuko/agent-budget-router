# Reference / Context Resolver 契約

> Status: Normative / Skill v1 design

## 責務

Resolverは通常指示からIssue ID、URL、外部参照を抽出し、Providerから取得した情報をHost非依存の共通文脈へ正規化する。

担当すること:

- 参照抽出
- Provider Resolverの選択
- 外部情報の取得結果の正規化
- `RESOLVED / PARTIALLY_RESOLVED / UNRESOLVED`の明示
- `task_context`と`source_identity`の生成

担当しないこと:

- タスク規模・予算判定
- `DIRECT / CONFIRM_FIRST / SPLIT / DEFER`の決定
- Agent起動・コード実装
- Host固有UI操作

## 正規化結果

```json
{
  "references": [
    {
      "type": "issue",
      "provider": "linear",
      "id": "MY-172",
      "resolution_status": "RESOLVED"
    }
  ],
  "task_context": {
    "title": "Issue title",
    "summary": "Normalized summary",
    "acceptance_criteria": [],
    "path_hints": [],
    "related_links": []
  },
  "source_identity": {
    "provider": "linear",
    "native_id": "provider-native-id",
    "identifier": "MY-172",
    "revision": "updatedAt-or-revision",
    "canonical_source_digest": "sha256"
  }
}
```

`task_context`はABR判定用、`source_identity`は同一性確認用であり、混同しない。要約生成結果はsource identityのdigest入力にしない。

## Provider拡張

Linear、GitHub、BacklogなどのProvider固有API・認証・エラー分類はResolver配下に閉じ込める。ABR CoreはProvider名やAPIを知らない。

