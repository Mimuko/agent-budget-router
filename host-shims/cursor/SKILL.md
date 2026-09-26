---
name: agent-budget-router
description: 明示的にタスク参照を解決し、Cursor input adapter経由で共通ABR preflightを実行する。
disable-model-invocation: true
---

# Agent Budget Router（Cursor shim）

このSkillはユーザーが明示的に呼び出した場合だけ使う。Cursorはconversation内のinvocation textを渡すため、Skill nameの後ろのtask textをadapterの`--task`引数へ変換する。
`skill_orchestrator.py`を直接起動したり、deprecatedなprompt Hookを呼び出したりしない。

## requestの実行

このSkill directoryの`scripts/cursor_adapter.py`を実行する。PowerShellの標準User配置では:

```powershell
python "$HOME/.cursor/skills/agent-budget-router/scripts/cursor_adapter.py" --task "<task text>"
```

このPoCでLinear Issueを参照する場合は、代わりにpersistent sessionを開始する:

```powershell
python "$HOME/.cursor/skills/agent-budget-router/scripts/cursor_adapter.py" --start-session --linear-backend orca --task "<task text>"
```

adapterは`cursor-session-id`をstderrに出力する。承認turnのためにそのIDを保持する。
これは共有Orchestratorの既存development backendを明示的に選択する。

adapterはtextを既存の`skill-v1` input JSONへ変換し、そのJSONを共有Orchestratorのstdinへ書き込み、JSON resultをstdoutへ出す。
成功時、人間向けサマリーをstderr末尾へ連続出力する（診断ログがある場合はsummaryより前）。
必須キー欠落はcontract violationとして扱い、通常summaryは出さずexit code 2で終了する。
また、このSkill directoryの`invocation-diagnostics.jsonl`へadapter pathとresult fieldsを書き込む。resultのstateとpolicyは変更せずに伝える。
`state`が`READY`かつ`forward.allowed`が`true`の場合だけtaskを転送する。

## 結果の表示

adapter実行後:

1. stderrの「実行前チェック結果」行から末尾までを抜き出し、先にチャットへ表示する。
   それより前のlog / warningやstderr全体は丸ごと転記しない。
2. ブロックが無い場合（contract violation・process error等）は失敗として伝え、
   タスクを転送しない。SKIP / READYに読み替えない。contract violation時はexit code 2。
3. stdoutのSkill v1 JSONは機械判断・技術詳細用に保持する。必要時のみ参照する。
4. 推奨方針・現在状態・実行可否の文言をAgentが独自に言い換えない。
5. `state`が`READY`かつ`forward.allowed`が`true`の場合だけタスクを転送する。
6. `NEEDS_CONFIRMATION`のときは承認を求め、承認後は既存のresume手順に従う。
7. parse error / process error / error付き応答 / contract violationをSKIPやREADYに読み替えない。

## 確認

Cursor chatでユーザーが承認した後、同じsession IDを再開する:

```powershell
python "$HOME/.cursor/skills/agent-budget-router/scripts/cursor_adapter.py" --resume-session "<cursor-session-id>" --approved true --task "<same task text>"
```

ユーザーが拒否した場合は`false`を使う。重複承認を確認する場合は、同じIDとtaskでresume commandを再実行する。
adapterは共有Orchestratorのerrorを伝え、別のREADYは発行しない。先の結果を承認した後に新しいsessionを起動しない。

start resultを読む。`NEEDS_CONFIRMATION`が返った場合はCursor conversationでユーザーに確認する。
background workerは待機中も元のOrchestrator processを保持する。parse errorやprocess errorを`SKIP`として扱わない。

このshimはCursor invocation textとtransportだけを扱う。共有Skill v1 contract、Core、Resolver、budget decisionは変更しない。
