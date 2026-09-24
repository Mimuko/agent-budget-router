---
name: agent-budget-router
description: 明示的なSkill呼び出しで外部参照を解決し、タスク規模・予算・実行方針をpreflightして呼び出し元Agentへ返す。実装・Issue分割・Agent起動は行わない。
---

# agent-budget-router

大きなタスクや外部Issue対応をAgentへ渡す前に、参照解決とABR preflightを行う論理共通Skill。
Cursor、Codex、Orcaでは、それぞれのSkill配置形式・manifest・shimから明示的に呼び出す。
物理的に同一packageをそのまま配布することは前提にしない。

## 正規の使い方

ユーザーまたは呼び出し元Agentが明示的に呼び出す。

```text
/agent-budget-router MY-172を実装して
```

軽微な単一ファイル修正など、preflightが不要な作業ではSkillを省略してよい。
transparent Hook、通常チャットの自動横取り、Agentの自動起動は正規経路ではない。

## Skillのワークフロー

1. 指示文を受け取る。
2. Reference / Context Resolverを呼び出す。
3. Resolverから`references`、`task_context`、`source_identity`、`resolution_status`を受け取る。
4. `should_preflight()`を呼び、小規模なら`SKIP`として軽量に終了する。
5. 必要な場合だけ`route()`を呼び、見積と実行方針を返す。
6. `CONFIRM_FIRST`または`SPLIT`では確認要求を返す。
7. 確認UI・入力は呼び出し元AgentまたはAgent別shimが担当する。
8. 承認結果を同一workflowへ戻し、ResolverとABR判定を再検証してから`READY`を返す。
9. 実装・実行は呼び出し元Agentが行う。

Skillはstdinで`y/N`を取得すること、コード変更、Issue分割、Agent / Model起動、Host固有UI操作を行わない。

## 共通結果

共通結果は次の契約に従う。

- `decision`: `SKIP | PREFLIGHT | INPUT_UNAVAILABLE`
- `resolution_status`: `NO_REFERENCE | RESOLVED | PARTIALLY_RESOLVED | UNRESOLVED`
- `state`: `READY | NEEDS_CONFIRMATION | BLOCKED`
- `execution_policy`: `DIRECT | CONFIRM_FIRST | SPLIT | DEFER`

`agent_action`は独立状態として返さず、呼び出し元Agentが`state`、`execution_policy`、
`forward.allowed`から派生する。

小規模タスクの例:

```json
{
  "decision": "SKIP",
  "resolution_status": "NO_REFERENCE",
  "state": "READY",
  "execution_policy": "DIRECT",
  "forward": { "allowed": true }
}
```

確認が必要な例:

```json
{
  "decision": "PREFLIGHT",
  "resolution_status": "RESOLVED",
  "state": "NEEDS_CONFIRMATION",
  "execution_policy": "CONFIRM_FIRST",
  "forward": { "allowed": false }
}
```

## 正本references

- [Skill責務・フロー](references/skill-contract.md)
- [共通I/O・状態・policy](references/io-contract.md)
- [Reference / Context Resolver](references/resolver-contract.md)
- [Linear Backend](references/linear-backend.md)
- [Migration / deprecated経路](references/migration.md)
- [見積ルール](references/estimation-rules.md)
- [実測スキーマ](references/measurement-schema.md)

ABR履歴にはprompt本文、Issue本文、会話全文、ソースコード、認証情報を保存しない。
