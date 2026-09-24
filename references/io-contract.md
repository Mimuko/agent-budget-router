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

## policy

`input_unavailable`と`reference_unresolved`で許可される値は、それぞれ次の3値だけである。

- `fail_open`
- `ask`
- `fail_closed`

初期既定値は両方とも`ask`とする。`INPUT_UNAVAILABLE`では`input_unavailable`、
`UNRESOLVED`または`PARTIALLY_RESOLVED`では`reference_unresolved`を適用する。
`PARTIALLY_RESOLVED`は、完全な`task_context`を保証できない限り、Skill v1では原則として
`reference_unresolved` policyの対象とする。実装側が独自判断で別policyや状態を選んではならない。

| policy | state | execution_policy | forward.allowed |
|:--|:--|:--|:--|
| `fail_open` | `READY` | `DIRECT` | `true` |
| `ask` | `NEEDS_CONFIRMATION` | `CONFIRM_FIRST` | `false` |
| `fail_closed` | `BLOCKED` | `DEFER` | `false` |

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

`INPUT_UNAVAILABLE`、`UNRESOLVED`、`PARTIALLY_RESOLVED`の状態マッピングは上記policyから
機械的に導出する。Skill Orchestrator、Resolver、Agent別shimは独自の状態選択を行わない。

参照解決不能時にIssue内容を推測しない。`ask`を初期既定値とし、呼び出し元Agentが確認できない場合は`NEEDS_CONFIRMATION / allowed=false`または`BLOCKED / allowed=false`で停止する。
