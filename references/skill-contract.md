# agent-budget-router Skill 契約

> Status: Normative / Skill v1 design
>
> 本書は、Cursor・Codex・Orcaから明示的に呼び出す論理共通Skillの責務と利用フローの正本である。
> 共通I/Oの詳細は`io-contract.md`、参照解決は`resolver-contract.md`を正とする。

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
- ABR Coreの`should_preflight()` / `route()`呼び出し
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

## 3. 確認

確認UI・入力は呼び出し元AgentまたはAgent別shimの責務とする。Skillがstdinで`y/N`を取得することは前提にしない。

`CONFIRM_FIRST`では、Skillは`NEEDS_CONFIRMATION`と確認内容を返す。承認結果が同一workflowへ戻った場合、ResolverとABR判定を再実行し、同じprompt・scope・source identityであることを確認してから`READY`へ進める。

promptまたはIssue内容が変わった場合、承認結果は無効として再評価する。別のSkill呼び出しへ承認を自動持越ししない。

## 4. Agent別shim

Cursor、Codex、Orcaで共有するのは、ABR Core・scripts・contracts・referencesという論理共通資産である。物理的な同一package配置やmanifest形式は前提にしない。

Agent別shimは呼び出し構文、配置形式、確認UI、結果表示を変換するだけで、Coreの判定やProvider接続を持たない。
