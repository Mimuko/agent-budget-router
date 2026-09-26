---
name: agent-budget-router
description: ユーザーが$agent-budget-routerを呼び出した場合だけ、Codex adapter経由で明示的なSkill v1 ABR preflightを実行する。
---

# Agent Budget Router（Codex shim）

Cursorも互換Skillとして`~/.agents/skills/`を探索する。Cursorでこのshimが選ばれた場合は、**Codex adapterを実行せず**、`~/.cursor/skills/agent-budget-router/scripts/cursor_adapter.py`を使い、Cursor shimの`SKILL.md`の手順に従う。Cursor shimが見つからなければ停止する。

`$agent-budget-router`の後ろのtask textをpromptとして扱う。このSkill directoryの`scripts/codex_adapter.py`を実行する。自然言語または空のstdinで共有Orchestratorを起動しない。PowerShellの標準User配置では:

通常のrequest:

```powershell
python "$HOME/.agents/skills/agent-budget-router/scripts/codex_adapter.py" --task "<task text>"
```

このPoCでLinear Issueを扱う場合は、persistent confirmation sessionを開始する:

```powershell
python "$HOME/.agents/skills/agent-budget-router/scripts/codex_adapter.py" --start-session --linear-backend orca --task "<task text>"
```

これは既存のdevelopment backendを明示的に選択する。出力された`codex-session-id`を次のturnまで保持する。返されたSkill v1 fieldsは変更せずに報告する。`preflight.recommended_policy`とworkflowの`execution_policy`を分けて保持する。

成功時、adapterは人間向けサマリーをstderr末尾へ連続出力する（診断ログがある場合はsummaryより前）。stdoutはSkill v1 JSONのみ。必須キー欠落はcontract violation（exit code 2、通常summaryなし）とする。

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

確認結果が返った場合は、taskを転送する前にユーザーの承認を求める。ユーザーが明示的に承認したら、同じsession IDを再開する:

```powershell
python "$HOME/.agents/skills/agent-budget-router/scripts/codex_adapter.py" --resume-session "<codex-session-id>" --approved true --task "<same task text>"
```

ユーザーが拒否した場合は`false`を使う。重複承認の確認を明示的に求められた場合は、同じIDとtaskでresume commandを再実行する。Orchestratorのresponseを報告する。先の結果を承認した後に新しいsessionを開始しない。preflight確認の一部としてtaskを実装しない。parse errorやprocess errorを`SKIP`へ変換しない。
