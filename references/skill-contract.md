# agent-budget-router Skill 契約

> Status: Normative / Skill v1 design
>
> 本書は、Cursor・Codex・Orcaから明示的に呼び出す論理共通Skillの責務と利用フローの正本である。
> 共通I/Oは`io-contract.md`、Core APIは`core-contract.md`、参照解決は`resolver-contract.md`を正とする。

## 1. 正規入口

transparent Hookによる自動横取りではなく、ユーザーまたは呼び出し元Agentが明示的に呼び出す。

```text
/agent-budget-router MY-172を実装して
```

小規模な単一ファイル修正など、明示的なpreflightが不要な作業ではSkillを省略できる。

## 2. 責務

Skill Orchestratorは次を担当する。

- 指示文の受付
- Reference Resolverの呼び出し
- Resolverから`references`、`task_context`、`source_identity`、`resolution_status`を受け取る
- ABR Coreの`should_preflight()` / `estimate_task()` / `route()`呼び出し
- `NEEDS_CONFIRMATION`と確認内容の返却
- Agentまたはshimから受け取った承認結果の同一workflow内再検証
- 共通I/O結果の返却

Skillは次を担当しない。

- 参照抽出
- Provider Resolverの選択
- Provider取得結果の正規化
- `task_context`生成
- `source_identity`生成
- コード変更・実装
- Issue分割内容やサブタスクの生成
- Agent / Modelの起動
- Cursor / Codex / Orca固有UI・内部API操作

## 3. Core呼び出しフロー

OrchestratorはResolverの結果を用意した後、まず`should_preflight(prompt, task_context?)`を呼ぶ。
外部参照がない場合は`task_context`なしで呼び出してよい。

```text
should_preflight(prompt, task_context?)
  ├─ SKIP
  │    → estimate_task()とroute()を呼ばない。詳細見積・budget snapshot取得・履歴処理を行わない
  │    → READY / execution_policy=DIRECT / forward.allowed=true
  ├─ PREFLIGHT
  │    → estimate_task(prompt, task_context?)を一度だけ呼び、TaskEstimateを得る
  │    → 同じTaskEstimateをBudget Cost Estimatorへ渡す
  │    → Estimatorが同一scope・quota window・総量基準の予測消費率を保証できる場合のみbudget_contextを構築
  │    → route(TaskEstimate, budget_context?)を呼び、recommended_policyを得る
  │    → workflow policyに従いstate、execution_policy、forward.allowedを決定
  └─ INPUT_UNAVAILABLE
       → estimate_task()とroute()を呼ばず、Orchestratorがinput_unavailable policyを適用
```

SKIP経路で利用枠取得は不要であり、詳細見積・履歴処理も行わない。例えば
`READMEの誤字修正して`がSKIPなら、`estimate_task()`も`route()`も呼ばずREADY / DIRECTで返す。
`PREFLIGHT`でbudget_contextを用意できない場合は省略し、TaskEstimateのbase recommendationを使う。
TaskEstimateは同一評価内のtask sizingのSingle Source of Truthであり、Orchestratorと`route()`は再見積しない。
確認後の再検証は新たな評価としてこの順序をやり直し、その評価内でも`estimate_task()`は一度だけ呼ぶ。

## 4. 確認

確認UI・入力は呼び出し元AgentまたはAgent別shimの責務とする。Skillがstdinで`y/N`を取得することは前提にしない。

`CONFIRM_FIRST`では、Skillは`NEEDS_CONFIRMATION`と確認内容を返す。承認結果が同一workflowへ戻った場合、ResolverとABR判定を再実行し、同じprompt・scope・source identityであることを確認してから`READY`へ進める。

promptまたはIssue内容が変わった場合、承認結果は無効として再評価する。別のSkill呼び出しへ承認を自動持越ししない。

## 5. Agent別shim

Cursor、Codex、Orcaで共有するのは、ABR Core・scripts・contracts・referencesという論理共通資産である。物理的な同一package配置やmanifest形式は前提にしない。

Agent別shimは呼び出し構文、配置形式、確認UI、結果表示を変換するだけで、Coreの判定やProvider接続を持たない。
