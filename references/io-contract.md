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

`task_context`はoptionalであり、外部参照がない通常タスク（`NO_REFERENCE`）では未設定のままCore判定へ進む。
`budget_context`はSkill呼び出しの必須入力ではない。`should_preflight()`が`PREFLIGHT`を返した場合に限り、
`estimate_task()`を一度だけ実行し、TaskEstimateを得る。必要に応じてCore外で残利用率を取得し、
Budget Cost Estimatorへ同じTaskEstimateを渡して今回タスクの予測消費率を算出する。その結果を
`budget_context`としてTaskEstimateとともに`route()`へ渡す。Orchestratorと`route()`はtask sizingを再実行しない。
token規模見積と利用率消費見積の責務を分離する。両比率は同一scope・quota window・総量基準を使い、
Budget Cost Estimator / normalizerがその一致または根拠ある消費率推定を保証できない場合は
`budget_context`を生成せず、TaskEstimateのbase recommendationへfallbackする。Coreは正規化済み
budget_contextの型・値域のみを検証する。schemaとCoreへの受け渡しは
[`core-contract.md`](core-contract.md)を正とする。

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

`ask`は常に`NEEDS_CONFIRMATION / CONFIRM_FIRST / forward.allowed=false`へ対応づける。
呼び出し元Agentが確認UIを提供できない場合も、この状態を変更せず、そのまま停止する。
`BLOCKED / DEFER`は`fail_closed`の場合にのみ使用する。

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
    "recommended_policy": "DIRECT",
    "task_class": "feature_build",
    "estimated_context": { "min": 42000, "max": 184000 },
    "estimated_generation": { "min": 8000, "max": 25000 },
    "base_recommendation": "DIRECT",
    "base_reason": "feature_build",
    "recommendation_reason": "budget_unavailable"
  },
  "forward": { "allowed": false }
}
```

`preflight.recommended_policy`はCoreのタスク・予算上の推奨（`DIRECT | SPLIT | DEFER`）を保持する。
`preflight`のtask sizing各値と`base_recommendation`・`base_reason`は一度生成したTaskEstimateから引き継ぐ。
トップレベル`reason`は`should_preflight`またはworkflow上の理由、`preflight.base_reason`は
TaskEstimate由来のtask sizing理由、`preflight.recommendation_reason`はrouteの最終推奨理由である。
budgetが推奨を引き上げた場合はbudget理由コードを、budget_context未提供時は
`budget_unavailable`を`recommendation_reason`に入れる。
トップレベル`execution_policy`はworkflow上の扱い（`DIRECT | CONFIRM_FIRST | SPLIT | DEFER`）を表す。
Skill v1は利用者の確認を必須にするため、Coreの`DIRECT`または`SPLIT`推奨を
トップレベル`CONFIRM_FIRST`で包み、Core推奨は`preflight.recommended_policy`に残す。
承認後のREADYは呼び出し元へタスクを渡す許可を意味し、分割内容の作成・Issue作成はSkillが行わない。
`DEFER`は確認だけで実行可能にならないため、トップレベルも`DEFER`のままにする。

`agent_action`は独立フィールドとして保持しない。必要な表示・分岐は`state`、`execution_policy`、`forward.allowed`から呼び出し元Agentが派生する。

## 列挙値と整合

- `decision`: `SKIP | PREFLIGHT | INPUT_UNAVAILABLE`
- `resolution_status`: `NO_REFERENCE | RESOLVED | PARTIALLY_RESOLVED | UNRESOLVED`
- `state`: `READY | NEEDS_CONFIRMATION | BLOCKED`
- `execution_policy`: `DIRECT | CONFIRM_FIRST | SPLIT | DEFER`
- `preflight.base_recommendation`: TaskEstimate由来の`DIRECT | SPLIT | DEFER`。budget_contextを反映しない。
- `preflight.base_reason`: TaskEstimate由来の非空の安定理由コード。
- `preflight.recommendation_reason`: routeの最終推奨理由コード。
- `preflight.recommended_policy`: `DIRECT | SPLIT | DEFER`。`CONFIRM_FIRST`は含めない。
- `READY`は`forward.allowed=true`のみ。
- `NEEDS_CONFIRMATION`と`BLOCKED`は`forward.allowed=false`のみ。
- `CONFIRM_FIRST`未承認は`NEEDS_CONFIRMATION`、承認・再検証後のみ`READY`。
- Coreの`recommended_policy = DIRECT`はworkflow上`CONFIRM_FIRST`で包める。
- トップレベル`execution_policy = SPLIT`の場合は分割計画が呼び出し元Agentで承認されるまで転送不可。
- Skill v1ではCoreの`recommended_policy = SPLIT`を`preflight`に保持し、利用者承認のworkflow gateはトップレベル`CONFIRM_FIRST`で表す。READY後の推奨適用は呼び出し元Hostの責務で、Skillは分割内容やIssueを生成しない。
- `DEFER`は承認だけで`READY`へ遷移しない。

`INPUT_UNAVAILABLE`、`UNRESOLVED`、`PARTIALLY_RESOLVED`の状態マッピングは上記policyから
機械的に導出する。Skill Orchestrator、Resolver、Agent別shimは独自の状態選択を行わない。

参照解決不能時にIssue内容を推測しない。`ask`を初期既定値とする。`ask`の場合、呼び出し元Agentが確認UIを提供できなくても`NEEDS_CONFIRMATION / CONFIRM_FIRST / forward.allowed=false`を維持して停止する。`BLOCKED / DEFER`を返すのは`fail_closed`の場合に限る。
