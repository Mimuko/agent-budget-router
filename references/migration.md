# Skill正規入口へのMigration

> Status: Normative migration guidance

## 現行資産の扱い

| 資産 | 移行後の扱い |
|:--|:--|
| ABR Core | Skillから利用するHost非依存Coreとして維持 |
| Reference Resolver / Linear Resolver | Skill前処理として維持。Backend分離へ変更予定 |
| `host-adapter-contract.md` | 旧Hook / Adapter互換契約として凍結 |
| `approval-resume-contract.md` | 非同期Hook互換の補助契約。Skill v1では同期確認を優先 |
| `linear-backend-strategy.md` | Skill用Backend選定記録へ移行 |
| Cursor Hook Adapter | deprecated。transparent gateの主経路にはしない |
| Cursor entrypoint capability | Hookが非保護・不安定であることの記録として維持 |
| Host Adapter | Skill Orchestratorへの移行対象。即時削除しない |

## 移行順序

1. Skill契約、I/O、Resolver、Linear Backend文書を確定する。
2. ABR Coreの`should_preflight()` / `route()`をHost非依存APIとして整理する。
3. Resolver / Linear Backend interfaceを分離する。
4. Skill Orchestrator単体PoCを行う。
5. Agent別shim / manifestを最小実装する。
6. Cursor・Codex・Orca横断PoCを行う。
7. Hook利用をdeprecatedとして案内する。
8. 利用実績確認後、旧Hook・approval-resume・旧出力形式の削除を判断する。

### Skill Orchestrator単体PoC

Agent別shimの問題とSkill Orchestrator本体の問題を分離するため、shim接続前に次だけを確認する。

- `READMEの誤字修正して`
  - `NO_REFERENCE`
  - `SKIP`
  - `READY / DIRECT`
- `MY-172を実装して`
  - `RESOLVED`
  - `PREFLIGHT`
  - `NEEDS_CONFIRMATION / CONFIRM_FIRST`

## 非対象

- transparent Hookの再実装
- Cursor Command / MCP App / Agent Window統合
- Codex wrapperの自動起動
- Skillによるコード変更・Issue分割・Agent起動
- 正式Linear Backendの先行決定
