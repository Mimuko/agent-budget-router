# Agent Budget Router

> **Estimate before you agent.**

Estimate token usage, task complexity, and an appropriate model/lane
before handing a large task to an AI coding agent.

## Why this exists

I gave a large AgentPlugin implementation task to a high-end agent model
and burned through the entire usage allowance before I could tell
whether the model was actually better.

## Key idea

```text
Repository size ≠ Expected agent context
```

A 1M-line repo with a one-file CSS fix is not the same as a 20-file
repo-wide architecture redesign. This skill estimates what the agent is
likely to *read and re-read*, not your whole workspace.

## Distribution

| Package | Files | Use with |
|---------|-------|----------|
| Cursor Skill (MVP) | `SKILL.md`, `references/`, `scripts/`, `catalog/` | Cursor Agent |
| OpenAI Skill compatible | + `agents/openai.yaml` | ChatGPT / Codex skill packages |

`scripts/abr.py` is the canonical daily CLI. Use it for the normal
`route → finish → stats` workflow; it keeps local state under
`~/.agent-budget-router/` and never stores prompts, transcripts, source code,
or credentials. The other scripts are auxiliary: `estimate.py` is the
backward-compatible standalone estimator, `compare_runs.py` is for controlled
Cursor/API-versus-Codex comparisons, and `scan_workspace.py` is an optional
input helper for estimation. They do not replace `abr.py` for daily routing.

Skill正規入口の責務・入出力・参照解決は、[Skill契約](references/skill-contract.md)、
[共通I/O契約](references/io-contract.md)、[Resolver契約](references/resolver-contract.md)を正本とする。
旧Host AdapterのI/Oは、[互換契約](../docs/architecture/host-adapter-contract.md)を参照する。

### Cursor Hook PoC

このリポジトリでは、`.cursor/hooks.json` の `beforeSubmitPrompt` が
`.cursor/hooks/abr_before_submit.py` を呼ぶ最小PoCを提供する。Hookは共通Host Adapterを
介して、軽微な依頼をそのまま送信し、`MY-<number>`形式の参照はLinear Resolverで取得してから
ABR Coreへ渡す。`CONFIRM_FIRST`や参照取得失敗（既定: `ask`）では送信を停止する。

PoCのLinear Resolverは、ログイン済みの `orca linear issue <id> --full --json` を利用する。
GitHub / Backlog Resolver、Codex wrapper、App Server、実際のタスク分割は対象外である。

## What it does

- Estimates **expected agent context** (not full repo token count)
- Applies exploration multipliers for re-read / subagent loops
- Returns **Go / Split / Defer** verdict
- Recommends phased execution (plan → implement → review)
- Separates model catalog from estimation logic
- Routes daily work from estimated context, live Codex allowance, and local performance history
- Keeps controlled Cursor → OpenAI API / Codex comparisons as a supporting analysis tool

## What it does NOT do

- Switch your chat model for you
- Guarantee billing accuracy
- Replace your team's routing policy

## Works well with

- [mimu-core](https://github.com/Mimuko/agent-plugins) routing-policy §7（役割）/ §8（Cursor Adapter, optional）
- Cursor subagents with pinned `model` + `effort` / `speed` in catalog

## 使い方（通常運用）

日常利用では `compare_runs.py` ではなく `abr.py` を使う。基本フローは
`configure（初回のみ）→ route → 実行 → finish → stats`。

### 0. 前提

- Python 3.10 以降
- Codex の利用枠を自動取得する場合は、`codex` コマンドが利用でき、ChatGPTアカウントでログイン済みであること
- コマンドは `agent-budget-router` ディレクトリをカレントディレクトリとして実行する

```powershell
cd agent-budget-router
```

### 1. Cursor API料金を設定する（初回・料金変更時のみ）

Cursor → OpenAI API の推定額も比較する場合、そのモデルに現在適用される
1M token当たりの料金を登録する。Codexだけを判定する場合、この手順は省略できる。

```powershell
python scripts/abr.py configure `
  --input-rate 4 `
  --cached-input-rate 0.4 `
  --output-rate 20 `
  --cached-input-ratio 0.2
```

料金は変動するため、利用時点の公式料金を指定する。上記の数値は入力例であり、
既定料金ではない。

### 2. タスク実行前にプリフライトする

通常の依頼文をそのまま渡す。

```powershell
python scripts/abr.py route "repo全体をレビューしてIssue候補を作る"
```

主な出力:

```text
Estimated task class: repository_review
Estimated input: 95k-636k tokens
Estimated output: 8k-25k tokens
Estimated Codex allowance impact: 3-5% (LOW)
Current Codex usage (measured): 29%
Remaining: 71%

Historical data
Similar tasks: 0
Median elapsed: no data
Accepted without revision: 0 / 0

Suggested execution: CODEX
Budget gate: CONFIRM / ASK_USER
Preflight ID: 5615d2a3-...
```

推定値と実測値は区別して表示する。`Current Codex usage` はCodexアカウントから
取得した実測値、`Estimated Codex allowance impact` は実行前の推定レンジ。

ゲートの意味:

| Gate | Action | 動作 |
|---|---|---|
| `NORMAL` | `AUTO_EXECUTE` | 低消費・残量十分・履歴精度が高い。統合エージェントはそのまま実行可能 |
| `CONFIRM` | `ASK_USER` | 中程度の消費、または履歴不足。実行先を確認 |
| `WARN` | `SUGGEST_ALTERNATIVE` | 高消費・残量不足・現在値取得不可。代替経路を提示して強く確認 |

対話端末では `CONFIRM` / `WARN` のとき、次の選択肢が表示される。

```text
Proceed? [Y] Codex / [C] Cursor API / [N] Cancel:
```

CIやエージェント統合から呼び出す場合は、対話を止めてJSONを受け取る。

```powershell
python scripts/abr.py route "タスク内容" --non-interactive --json
```

統合側は `gate.action` を確認してからタスクを起動する。`abr.py` 自体はCodexや
Cursorのタスク実行ランチャーではない。

### 標準プロンプトから呼び出す

Cursor / Codexの通常の依頼文は、次のいずれか一つで渡す。本文は推定にだけ使われ、
ABRのローカル履歴には保存されない。

```powershell
# 直接引数（短い依頼文）
python scripts/abr.py route "mimu-coreのRouting Policyをレビューする" --json --non-interactive

# stdin（Hostの標準プロンプト連携）
Get-Content .\prompt.txt -Raw | python scripts/abr.py route --stdin --json --non-interactive

# UTF-8ファイル（長い依頼文）
python scripts/abr.py route --task-file .\prompt.txt --json --non-interactive
```

統合側はstdoutのJSONだけを読み、`gate.action`を判断材料にする。`AUTO_EXECUTE`でも
実行自体はHostが担い、`ASK_USER` / `SUGGEST_ALTERNATIVE`では確認または代替経路を提示する。
`--stdin`、`--task-file`、直接引数は同時に指定できない。

### 3. 選択した経路でタスクを実行する

表示された `Preflight ID` を控え、CodexまたはCursorでタスクを実行する。
このIDにはプロンプトやソースコードは保存されない。

### 4. 実行後にプリフライトを閉じる

実行後、同じ `Preflight ID` を指定する。これによりCodex利用率のafter snapshotを
取得し、beforeとの差分と実行結果を履歴化する。

```powershell
python scripts/abr.py finish 5615d2a3-... `
  --route codex `
  --completion completed `
  --acceptance satisfied `
  --elapsed-minutes 13 `
  --tests passed `
  --lint passed `
  --build passed `
  --human-revisions 0 `
  --parallel-activity none
```

`--parallel-activity` の指定:

| 値 | 意味 | 推定への利用 |
|---|---|---|
| `none` | 同時間帯に他のCodex実行がない | `HIGH` attributionとして次回推定に利用 |
| `detected` | 他のCodex実行があった | アカウント全体の参考値としてのみ保存 |
| `unknown` | 並行実行の有無を確認できない | アカウント全体の参考値としてのみ保存 |

判断できない場合は既定の `unknown` のままにする。同じPreflight IDを二重に
`finish` することはできない。

### 5. 履歴を確認する

```powershell
python scripts/abr.py stats
```

タスク種別・経路ごとに実行件数、コスト中央値、所要時間中央値、受入率を表示する。
タスク帰属可能なCodex利用率差分は、同種タスク3件で `MEDIUM`、6件で `HIGH`
confidenceとなり、以降の allowance impact 推定レンジへ反映される。

### 補助コマンド

現在のCodex利用枠とグローバル使用量だけをスナップショット保存する:

```powershell
python scripts/abr.py capture-codex
```

プリフライトを使わず、既存の自動化hookから実行結果だけを記録する:

```powershell
python scripts/abr.py record `
  --task-class repository_review `
  --route codex `
  --completion completed `
  --acceptance satisfied `
  --elapsed-minutes 12 `
  --tests passed
```

ローカル状態は `~/.agent-budget-router/` に保存する。プロンプト、会話本文、
ソースコード、APIキーは保存しない。

### 実測補正の運用

`route`の `estimated_context` / `estimated_generation` / `estimated_allowance_impact` は
実行前の推定値であり、請求額や厳密な利用量ではない。実行後は、プリフライトがある場合は
同じIDで `finish`し、ない場合は `record`する。`finish`はCodexのbefore/after利用率と
完了・受入・テスト結果を保存し、並行実行が不明な場合は帰属を `UNCERTAIN` として補正に使わない。
`stats`で同種タスクの中央値と受入率を確認し、3件未満は低〜中信頼度、6件以上の帰属可能な
実測差分で高信頼度として次回の推定へ反映する。

## Quick start（従来の見積コマンド）

### Cursor

```bash
# Install
git clone https://github.com/Mimuko/agent-budget-router.git \
  ~/.cursor/skills/agent-budget-router

# Or symlink from this monorepo
ln -s "$(pwd)/agent-budget-router" ~/.cursor/skills/agent-budget-router
```

In Cursor Agent chat:

```text
Estimate this task before agent:
Implement a new HubSpot module for the pricing table component.
```

Or run the script directly:

```bash
python scripts/estimate.py "Fix typo in README.md" --json
```

### With workspace scan (optional)

```bash
python scripts/scan_workspace.py --root . --hint mimu-core/ --json > /tmp/scan.json
python scripts/estimate.py "Refactor routing-policy across plugins" \
  --scan-json /tmp/scan.json --skill-count 8
```

## Architecture

```text
User task
  → agent-budget-router (pre-flight estimate)
    → Go / Split / Defer
      → routing-policy Lanes (post-decision delegation)
        → implementer | analyst-planner | cross-reviewer
```

## Catalog design

Model identity and runtime settings are separated:

```yaml
# catalog/models.default.yaml
models:
  cursor-grok-4.6:
    effort_levels: [low, medium, high, xhigh]
    speed_modes: [standard, fast]

# catalog/lanes.default.yaml
lanes:
  analyst-planner:
    model: cursor-grok-4.6
    effort: high
    speed: standard
```

No synthetic IDs like `cursor-grok-4.6-high-fast` in the catalog.

## Estimation formula

```text
Estimated Context
  = Task baseline
  + Expected relevant files
  + Instruction / Skill overhead
  + Re-read / exploration factor
```

Exploration multipliers (v1):

| Pattern | Multiplier |
|---------|------------|
| single-file edit | ×1.1 – 1.3 |
| known feature area | ×1.3 – 1.6 |
| cross-cutting change | ×1.5 – 2.0 |
| architecture / unknown repo | ×1.8 – 3.0 |

Details: [references/estimation-rules.md](references/estimation-rules.md)

## Examples

| Example | Verdict | Pattern |
|---------|---------|---------|
| [small-fix.md](examples/small-fix.md) | GO | single-file edit |
| [feature-build.md](examples/feature-build.md) | GO | known feature area |
| [large-agent-task.md](examples/large-agent-task.md) | SPLIT_RECOMMENDED | architecture |

## Development

```bash
python -m pytest tests/
python scripts/estimate.py --task-file examples/small-fix.md
python scripts/compare_runs.py --cursor examples/measurements/cursor-api.json \
  --codex examples/measurements/codex-included-plan.json
```

## Observed cost comparison

After running the same task through both routes, record only the observed usage,
completion, elapsed time, and quality score. Then run `compare_runs.py`.

- Cursor API: use the observed `api_cost_usd`; if unavailable, provide the
  observed input / cached-input / output tokens and the rates that applied then.
- Codex: record whether the run used included plan allowance or additional
  credits. Included allowance is not treated as a zero-dollar task price.
- A route recommendation is emitted only when both tasks completed at comparable
  quality and both marginal USD values are available.

See [measurement schema](references/measurement-schema.md) and runnable
[examples](examples/measurements/).

## Daily routing

Use `abr.py` as the normal interface; `compare_runs.py` is for the initial
paired experiments only.

```bash
python scripts/abr.py route "repo全体をレビューしてIssue候補を作る"
# 選択した経路で実行し、表示された Preflight ID を使って閉じる
python scripts/abr.py finish <preflight-id> \
  --route codex --completion completed --acceptance satisfied \
  --tests passed --parallel-activity unknown
python scripts/abr.py stats
```

`abr route` estimates the task as before, reads the currently logged-in Codex
plan/rate-limit state through `codex app-server`, and applies median facts from
prior runs of the same task class. It recommends `CODEX` at medium confidence
when plan allowance is available; confidence becomes high after three accepted
comparable Codex runs. It does not claim that a fixed ChatGPT plan has a zero
per-task price.

The route result is also a preflight budget gate:

- `NORMAL / AUTO_EXECUTE`: low estimated impact, enough remaining allowance,
  and high-confidence comparable history.
- `CONFIRM / ASK_USER`: moderate impact or incomplete calibration.
- `WARN / SUGGEST_ALTERNATIVE`: high impact, low remaining allowance, or no
  readable live allowance.

Allowance impact is always shown as a range. Before attributable history
exists, a conservative task-class prior is marked `LOW` confidence. Three
attributable runs raise it to `MEDIUM`; six raise it to `HIGH`.

To automatically retain a privacy-safe Codex account snapshot (current plan
allowance and global token-activity summary), run this before/after a work
session or from an automation hook:

```bash
python scripts/abr.py capture-codex
```

The snapshot is global account telemetry, not a per-task attribution. The
router never silently assigns unrelated concurrent usage to a task.

`route` saves a privacy-safe before snapshot and prints a Preflight ID. Close it
after execution to capture the after snapshot and observed account delta:

```bash
python scripts/abr.py finish <preflight-id> \
  --completion completed --acceptance satisfied --elapsed-minutes 13 \
  --tests passed --parallel-activity none
```

Only `--parallel-activity none` produces a high-confidence task-attributable
delta. `detected` and `unknown` remain account-level observations and are not
used to calibrate the next task estimate.

For Cursor API cost estimates, configure the current rates once (this writes
internal local state; you do not create a JSON file):

```bash
python scripts/abr.py configure \
  --input-rate 4 --cached-input-rate 0.4 --output-rate 20 \
  --cached-input-ratio 0.2
```

Use the rates applicable to the actual Cursor API model at the time; the
router intentionally does not embed volatile price data.

If an automation hook cannot create or close a preflight, use `record` as the
alternative outcome-only path. Do not use `record` and `finish` for the same
run; `finish` is the canonical path when a preflight exists.

```bash
python scripts/abr.py record --task-class repository_review \
  --route codex --completion completed --acceptance satisfied \
  --elapsed-minutes 12 --tests passed --lint passed --build passed
```

The local history contains no prompts, transcripts, source code, or secrets.
`quality_score` is optional; acceptance criteria and test/lint/build results
are the primary performance signals.

## License

MIT — see [LICENSE](LICENSE)
