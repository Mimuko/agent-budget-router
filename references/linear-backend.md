# Linear Backend 方針

> Status: Decision Pending
>
> 本書はSkillから利用するLinear Backendの比較正本である。正式Primaryはread-only Spike後にDecisionを追記する。

## Interface

```text
fetch_issue(identifier) -> BackendIssue | BackendError
```

`BackendIssue`はprovider-native ID、identifier、title、description、URL、updatedAtまたはrevision、source identity生成に必要なsource fieldsを返す。`BackendError`は`not_found`、`auth_unavailable`、`network_error`、`partial`を区別する。

## 候補

| 候補 | 扱い |
|:--|:--|
| Linear公式MCP endpoint直接接続 | 第一候補としてread-only接続を評価 |
| Linear GraphQL API | 認証、source identity、移植性を比較 |
| Cursor MCP bridge | Cursor Agentの非公開RPCに依存しない場合だけ候補 |
| Orca backend | 開発fallback。通常利用の必須依存にしない |

認証情報は環境変数またはcredential storeから取得し、Skill資産、manifest、リポジトリ、ログへtokenを含めない。

## Decision記録

| 項目 | 状態 |
|:--|:--|
| Primary backend | 未確定 |
| Fallback backend | Orca候補・未確定 |
| 認証方式 | 未確定 |
| 根拠 | Spike後に追記 |

