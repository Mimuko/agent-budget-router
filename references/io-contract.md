# agent-budget-router 共通I/O契約

> Status: Normative / Skill v1 design

## 入力

```json
{
  "schema_version": "skill-v1",
  "prompt": "LinearのMY-172を実装して",
  "prompt_available": true,
  "references": [],
  "workspace_scope": "workspace-id-or-root",
  "repository_scope": "git-root-and-worktree",
  "policy": {
    "input_unavailable": "ask",
    "reference_unresolved": "ask"
  }
}
```

Resolver実行後、内部的に`references`、`task_context`、`source_identity`を補完する。`source_identity`はABR Coreへ渡さず、同一workflowの再検証にだけ使う。

## 出力

```json
{
  "schema_version": "skill-v1",
  "decision": "PREFLIGHT",
  "resolution_status": "RESOLVED",
  "state": "NEEDS_CONFIRMATION",
  "execution_policy": "CONFIRM_FIRST",
  "reason": "cross_cutting",
  "preflight": {
    "task_class": "feature_build",
    "estimated_context": { "min": 42000, "max": 184000 },
    "estimated_generation": { "min": 8000, "max": 25000 }
  },
  "forward": { "allowed": false }
}
```

`agent_action`は独立フィールドとして保持しない。必要な表示・分岐は`state`、`execution_policy`、`forward.allowed`から呼び出し元Agentが派生する。

## 列挙値と整合

- `decision`: `SKIP | PREFLIGHT | INPUT_UNAVAILABLE`
- `resolution_status`: `NO_REFERENCE | RESOLVED | PARTIALLY_RESOLVED | UNRESOLVED`
- `state`: `READY | NEEDS_CONFIRMATION | BLOCKED`
- `execution_policy`: `DIRECT | CONFIRM_FIRST | SPLIT | DEFER`
- `READY`は`forward.allowed=true`のみ。
- `NEEDS_CONFIRMATION`と`BLOCKED`は`forward.allowed=false`のみ。
- `CONFIRM_FIRST`未承認は`NEEDS_CONFIRMATION`、承認・再検証後のみ`READY`。
- `SPLIT`は分割計画が呼び出し元Agentで承認されるまで転送不可。
- `DEFER`は承認だけで`READY`へ遷移しない。

参照解決不能時にIssue内容を推測しない。`ask`を初期既定値とし、呼び出し元Agentが確認できない場合は`NEEDS_CONFIRMATION / allowed=false`または`BLOCKED / allowed=false`で停止する。

