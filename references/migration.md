# Skill正規入口への移行

> 状態: Skill v1移行PoCは完了。正式なLinear Backendの選定は未完了。
>
> 本書は現在の移行状態を記録する。実行時の正本は以下の契約文書とする。

## 現在の構成

Skill v1の正規入口は、ユーザーまたは呼び出し元Agentによる明示Skill呼び出しである。共通I/O、Resolver、ABR Core、Skill Orchestratorを分離し、Cursor / Codex / Orca固有の呼び出し構文・登録・確認UIは各shimに置く。

| 資産 | 現在の扱い |
|:--|:--|
| Skill契約・共通I/O | `skill-contract.md` と `io-contract.md` をSkill v1の正本として使用 |
| ABR Core | Host / Provider / UIに依存しないCoreとして分離済み |
| Reference Resolver | 参照抽出、Provider選択、取得結果の正規化を担当。`task_context` と `source_identity` を区別 |
| Linear Backend interface | Resolverから利用するinterfaceとして分離済み。正式Primary backendは未選定 |
| Skill Orchestrator | Resolver → Core判定 → workflow状態・転送可否の調停を担当 |
| Agent別shim | invocation、登録、共通I/Oへの変換、確認UI、session handling、結果表示を担当。Core判定とProvider接続は持たない |
| [host-adapter-contract.md](../../docs/architecture/host-adapter-contract.md) | deprecatedな旧Hook / Host Adapterとの互換・移行資料。即削除しない |
| [approval-resume-contract.md](../../docs/architecture/approval-resume-contract.md) | 旧非同期Hook経路の互換資料。Skill v1の確認・再検証契約は `skill-contract.md` が正本 |
| Cursor `beforeSubmitPrompt` Hook | `.cursor/hooks.json` では無効化済み。Skill v1の正規入口ではなく、残る旧実装はdeprecatedな互換・移行資産として扱う |

Orca Linear Backendは開発PoC用fallbackであり、Cursor / Codexの実機確認では明示設定して使用した。通常利用にOrcaを必須とせず、本番backendの決定はread-only Spike後まで保留する。この保留はPoCの完了条件と矛盾しない。

## 完了済みの移行ステップ

| Linear issue | 完了内容 |
|:--|:--|
| MY-213 | Skill v1契約、共通I/O、Resolver、Linear Backend方針、deprecated経路とshim境界を文書化 |
| MY-214 | ABR Core・Resolver・Skill Orchestratorを分離し、TaskEstimateとreason / policyの責務を定義 |
| MY-215 | Orca・Cursor・CodexでCase A / Case Bと承認フローを確認。各Agentのshim / invocation経路で共通出力・状態語彙を確認 |

MY-215のPoC確認結果:

- Case A (`READMEの誤字修正して`): `SKIP`, `NO_REFERENCE`, `READY`, `DIRECT`, `forward.allowed=true`
- Case B (`MY-172を実装して`、明示したPoC backendを使用): `RESOLVED`, `PREFLIGHT`, `NEEDS_CONFIRMATION`, `CONFIRM_FIRST`, `forward.allowed=false`
- Case Bの`preflight.recommended_policy`はCore推奨（`DIRECT | SPLIT | DEFER`）として保持し、workflowの`execution_policy`である`CONFIRM_FIRST`と区別
- 承認後は同一workflow内でResolverと判定を再実行し、prompt / scope / source identityを再検証して`READY / forward.allowed=true`へ遷移
- 同一承認結果の再送ではpending confirmationが消費済みのため、`READY`を再発行しない

これらの確認はruntime PoCの結果であり、Skillがタスク実装、Issue分割、Agent起動を行うことを意味しない。状態・policy・reasonの対応は `io-contract.md` と `skill-contract.md` を正とする。

## 旧Hook経路の扱い

- transparent Hookは有効な入口として使わず、Skill v1は明示Skill invocationを正規入口とする。旧Cursor `beforeSubmitPrompt` Hookは無効化済み。
- 旧Hook / Host Adapter契約は互換資料として残す。これらはSkill v1の共通I/Oやworkflow判定を変更しない。
- 旧Hookや旧出力形式を削除する作業はこのPoCに含めない。移行先の利用実績と互換要件を確認してから、別途削除を判断する。

## 残課題

- Linear Backend候補をread-onlyで比較し、正式Primary、認証方式、fallback方針を決定記録へ反映する。
- 旧Hook / Host Adapterの削除要否を、Skill v1への移行実績と互換要件に基づいて判断する。

production backendの選定、Hook廃止、運用実績に依存する判断はSkill v1移行完了を阻害しない。MY-212の完了条件には含めない。

## 非対象

- transparent Hookの再実装または本PoC内での削除
- Cursor Command / MCP App / Agent Window統合
- Codex wrapperの自動起動
- Skillによるコード変更・Issue分割・Agent起動
- read-only Spike前の本番Linear Backend選定・本番接続
