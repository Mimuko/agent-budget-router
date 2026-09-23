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
2. ABR Coreの`should_preflight()` / `route()`を共通Skill入口から呼べる形に整理する。
3. Linear Backend interfaceとResolverを分離する。
4. Agent別shim / manifestを作成し、Cursor・Codex・Orcaの明示呼び出しを接続する。
5. `SKIP`とLinear参照付き`CONFIRM_FIRST`を最小PoCで確認する。
6. Hook利用をdeprecatedとして案内する。
7. 利用実績と互換性を確認後、旧Hook・旧approval resume・旧出力形式の削除を判断する。

## 非対象

- transparent Hookの再実装
- Cursor Command / MCP App / Agent Window統合
- Codex wrapperの自動起動
- Skillによるコード変更・Issue分割・Agent起動
- 正式Linear Backendの先行決定

