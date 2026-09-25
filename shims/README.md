# Host shim契約（PoC）

確認状態: MY-215のworktreeでOrca、Cursor、Codexの実行を確認済み。

共通interfaceは各Hostを`scripts/skill_orchestrator.py`とその`skill-v1` JSON結果へ接続する。
shimはHost固有の明示Skill invocation、確認UI、結果表示だけをこのprotocolへ変換する。
`forward.allowed`がfalseの結果を実行許可として解釈してはならない。

## Invocation対応

| Host | 明示invocation | Shimの責務 |
|:--|:--|:--|
| Cursor | `/agent-budget-router <task>` | `.cursor/skills/agent-budget-router/SKILL.md`のProject SkillがCursor adapterを使い、chat turnをまたいで確認sessionを保持する。 |
| Codex | `$agent-budget-router <task>` | `.agents/skills/agent-budget-router/SKILL.md`のProject SkillがCodex adapterを使い、turnをまたいで確認sessionを保持する。 |
| Orca | 設定済みの`agent-budget-router` Skillを明示的に呼び出す | Orca CLI sessionを確認済み。GUI Skill surfaceは対象外。 |

共有packageは論理的な単位である。各Hostは固有のSkill discovery形式で導入してよい。
Hook、自動invocation、child-agent launch、対象タスクの実装はこのshim契約に含めない。

## 確認session

`agent-budget-router/`から長時間動作するOrchestrator processを1つ起動する:

```text
python scripts/skill_orchestrator.py --session
```

JSON lineを1行送り、JSON結果を1つ読む:

```json
{"action":"start","request":{"prompt":"READMEの誤字修正して","prompt_available":true}}
```

確認が必要なタスクでは同じprocessを保持し、Hostの通常の確認UIを表示する。承認後、ユーザーの判断を付けて元のrequestを再送する:

```json
{"action":"resume","request":{"prompt":"MY-172を実装して","prompt_available":true},"approved":true}
```

Orchestratorは結果を返す前に参照解決とCore判定を再実行する。Hostがタスクを転送できるのは`state: READY`かつ`forward.allowed: true`の場合だけである。
prompt、workspace、repository、Linear source、またはCore判定が変わった場合、承認は無効になる。各pending confirmationへの承認はsingle-useである。
再検証で新しい`NEEDS_CONFIRMATION`結果になった場合は新しいpending fingerprintを保存し、同じsessionで新しい承認を受けられる。
`READY`への遷移または拒否で消費された承認は再送できない。

## Local Linear PoC（開発fallback）

既定のCoreはLinearへ暗黙接続しない。Orca Linearへアクセスできる開発checkoutでは、PoC processで明示的に有効化する:

```powershell
$env:ABR_LINEAR_BACKEND = "orca"
python scripts/skill_orchestrator.py --session
```

これは`orca linear issue <id> --full --json`を通して読む。開発fallback専用であり、正式なLinear backendは未選定である。
明示設定がない場合、参照Issueはunresolvedとして返り、既定の`ask` policyにより転送されない。

## 固定ケース

| Request | 共通結果の期待値 |
|:--|:--|
| `READMEの誤字修正して` | `NO_REFERENCE`, `SKIP`, `READY`, `DIRECT`, allowed `true` |
| `MY-172を実装して`（local Orca backend） | `RESOLVED`, `PREFLIGHT`, `NEEDS_CONFIRMATION`, `CONFIRM_FIRST`, allowed `false` |
| 承認後、Linear sourceが変わらない同じrequest | `READY`, allowed `true`、1回だけ |

共通codeとI/O契約が1つの結果語彙を定義する。Orca、Cursor、Codexのruntime確認ではCase A、Case B、承認後のREADY、承認再送の拒否を確認済みである。

## Lifecycleとlocal stateの扱い

CursorとCodexのpersistent adapterには、意図した2つの待機windowがある:

- 初回承認commandを待つ間は600秒。
- 各command後、次のcommandを待つ間は120秒。

これらはPoC transportの制限であり、承認やworkflow policyではない。windowが切れるとworkerはchild Orchestrator processを終了し、sessionを再開始する必要がある。
承認または拒否が完了するとworkflowは消費されるが、workerは次のcommand timeoutまたはprotocol errorまで利用可能な状態を保つ。承認再送はOrchestratorが拒否する。

adapterはlocal `.sessions/<id>/` directoryに`configuration.json`、command file、response fileを書き込む。
同じrequestを再検証できるよう、configurationにはtask promptとworkspace/repository scopeが含まれる。このdirectoryはlocal sensitive stateとして扱う。
Gitでは無視されるが、PoCには完了後またはtimeout後の自動削除・redactionはまだない。期限切れsession directoryはHostのlocal retention policyに従って削除する。
自動TTL cleanupとprompt/scope redactionは、このPoCの範囲外のfollow-up項目である。
