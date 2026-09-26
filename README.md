# Agent Budget Router

> **Agentへ渡す前に見積もる。**

## Cursor / CodexのUser scopeへインストール

配布リポジトリをcloneした後、PowerShellで実行する。Python 3が必要。

```powershell
git clone https://github.com/Mimuko/agent-budget-router.git
cd agent-budget-router
./install.ps1 install
./install.ps1 update      # 配布repoを更新した後
./install.ps1 uninstall   # 管理下のインストールを削除
./install.ps1 rollback    # 直前の版を復元
```

インストーラは共有Coreを`~/.agent-budget-router/agent-budget-router/`へ1部、Cursor shimを`~/.cursor/skills/agent-budget-router/`、Codex shimを`~/.agents/skills/agent-budget-router/`へ配置する。`~`は実行ユーザーのhome。案件repoへはコピーしない。既存の管理外Skillやsymlinkは上書きせず停止する。更新・削除の前の版は`~/.agent-budget-router/backups/`に保持し、`rollback`で復元できる。Skillの再読込には新しいCursor/Codex sessionを開始する。

Cursorの公式探索先はprojectの`.cursor/skills/`とUserの`~/.cursor/skills/`、Codexの公式探索先はrepoの`.agents/skills/`とUserの`~/.agents/skills/`。[Cursor Skills](https://prod.cursor.com/docs/skills)、[OpenAI Docs: Build skills](https://learn.chatgpt.com/docs/build-skills)を参照。Codexでは同名Skillは結合されず、双方が候補に出る。Cursorは互換性のため`~/.agents/skills/`も探索し、実機では同名のCodex shimを選ぶケースを確認した。User配布版のCodex shimにはCursorで選ばれたときCursor shimへ誘導する手順を含める。Cursorの同名Skillについて公式資料に選択優先順位の保証は見当たらない。このため開発checkoutで確実にworkspace-local版を使うときは、Skill候補のパスを確認し、`.cursor/skills/agent-budget-router/`または`.agents/skills/agent-budget-router/`のadapterを明示実行する。User版shimはインストール済みCoreを参照し、workspace-local版shimはcheckout内のCoreを参照する。通常案件やOrca workspaceではUser版を使う。

ローカルのCursor AgentにはUser Skillが見える。Cursor Cloud Agent、remote SSH、self-hosted workerにはローカルSkillが自動配布されない。必要ならCursorのSync Skillsを別途設定する。[Cursor Skills](https://prod.cursor.com/docs/skills)を参照。

大きなタスクをAI coding agentへ渡す前に、token使用量、タスクの複雑さ、適切なmodel/laneを見積もる。

## 目的

大きなAgentPlugin実装タスクを高性能なagent modelへ渡したところ、そのmodelが本当に優れているか判断する前に利用枠を使い切った。

## 基本の考え方

```text
Repository size ≠ Expected agent context
```

1M行のrepoで1ファイルのCSSを修正する作業は、20ファイルにまたがるrepo全体のarchitecture redesignとは異なる。
このSkillはworkspace全体ではなく、agentが*読む・読み直す*可能性の高い範囲を見積もる。

## 配布

| パッケージ | ファイル | 使用先 |
|---------|-------|----------|
| Cursor Skill (MVP) | `SKILL.md`, `references/`, `scripts/`, `catalog/` | Cursor Agent |
| OpenAI Skill compatible | + `agents/openai.yaml` | ChatGPT / Codex skill packages |

開発・統合の正本は monorepo `agent-plugins` の本ディレクトリ。公開配布先は別リポジトリ
[`Mimuko/agent-budget-router`](https://github.com/Mimuko/agent-budget-router) である。
merge までは自動化せず、人間が差分を確認してから配布先へ merge する。

### 配布対象 / 非対象

| 配布する（この package） | monorepo 側に残す |
|:--|:--|
| Core / Resolver / Orchestrator / `references/` / `catalog/` / `scripts/` / `tests/` / `examples/` | `.cursor/skills/agent-budget-router/`（Cursor Host shim） |
| `shims/`（Host 共通契約） | `.agents/skills/agent-budget-router/`（Codex Host shim） |
| `SKILL.md` / `README.md` / `LICENSE` / `agents/openai.yaml` など package 直下 | 他 Plugin・root marketplace・monorepo docs |

### monorepo から配布先へ同期する

repository root で実行する。

```bash
# 差分確認のみ（push / PR なし）
bash scripts/sync-agent-budget-router-dist.sh --dry-run

# sync branch を push し、配布先へ PR を作成
bash scripts/sync-agent-budget-router-dist.sh
```

スクリプトは `git subtree split --prefix=agent-budget-router` で package だけを切り出し、
Host 固有 shim が混入していないことを検証してから `sync/abr-<date>-<sha>` ブランチを
`Mimuko/agent-budget-router` へ push し、`gh pr create` する。作業ツリーが dirty なときは
失敗する（必要な場合だけ `--allow-dirty`）。

`scripts/abr.py`が日常運用のcanonical CLIである。通常の`route → finish → stats` workflowに使い、local stateを`~/.agent-budget-router/`に保持するが、prompt、transcript、source code、credentialは保存しない。
他のscriptは補助用で、`estimate.py`は後方互換のstandalone estimator、`compare_runs.py`はCursor/APIとCodexの比較用、`scan_workspace.py`は見積用の任意input helperである。日常のroutingでは`abr.py`を置き換えない。

Skill正規入口の責務・入出力・参照解決は、[Skill契約](references/skill-contract.md)、
[共通I/O契約](references/io-contract.md)、[Resolver契約](references/resolver-contract.md)を正本とする。
旧Host AdapterのI/Oは、[互換契約](../docs/architecture/host-adapter-contract.md)を参照する。
Cursor / Codex / Orcaの薄いshimと、同一プロセスで確認を再開するJSONL手順は[Host shim PoC](shims/README.md)を参照する。

### deprecated Cursor Hook PoC

旧 `beforeSubmitPrompt` 用の実装 `.cursor/hooks/abr_before_submit.py` は移行資料として残っているが、
`.cursor/hooks.json` の `hooks` は空であり、Hookは無効化済みである。これはSkill v1の正規入口ではなく、
透明なHook gateを新しい主経路として拡張しない。

### Skill v1の正規入口

通常の自動横取りではなく、`/agent-budget-router ...` のような明示的なSkill呼び出しを正規入口とする。
Skill v1の責務、I/O、Resolver境界、Linear Backend戦略、移行順序は、上記の契約文書を正本として参照する。

PoCのLinear Resolverは、ログイン済みの `orca linear issue <id> --full --json` を利用する。
GitHub / Backlog Resolver、Codex wrapper、App Server、実際のタスク分割は対象外である。

## できること

- **expected agent context**（repo全体のtoken数ではない）を見積もる
- 読み直しやsubagent loopの探索係数を適用する
- **Go / Split / Defer**の判定を返す
- 段階的な実行（plan → implement → review）を推奨する
- model catalogと見積ロジックを分離する
- 見積context、Codexの現在の利用枠、local performance historyから日常作業をroutingする
- Cursor → OpenAI API / Codexの制御比較を補助分析として保持する

## しないこと

- chat modelを自動で切り替える
- billing accuracyを保証する
- teamのrouting policyを置き換える

## 相性のよい構成

- [mimu-core](https://github.com/Mimuko/agent-plugins) routing-policy §7（役割）/ §8（Cursor Adapter, optional）
- catalogで`model` + `effort` / `speed`を固定したCursor subagents

## 使い方（通常運用）

日常利用では `compare_runs.py` ではなく `abr.py` を使う。基本フローは
`configure（初回のみ）→ route → 実行 → finish → stats`。

共通Skillの入出力PoCは `scripts/skill_orchestrator.py --session` を使う。確認UIは呼び出し元Hostが担当し、
承認後は同じプロセスへ元の要求と承認結果を返す。Cursor、Codex、Orca間でJSON契約と状態語彙は共通である。
参照なしの小規模タスクは `SKIP / READY / DIRECT`、Linear参照タスクは解決後にCoreの推奨と確認状態を返す。
Linear接続のOrca開発fallbackは `ABR_LINEAR_BACKEND=orca` を明示したときだけ有効になる。

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

## クイックスタート（従来の見積コマンド）

### Cursorで使う

```bash
# 正式インストールは上記の install.ps1 を使う
./install.ps1 install
```

Cursor Agent chatで:

```text
Agentへ渡す前にこのタスクを見積もる:
pricing table component用の新しいHubSpot moduleを実装する。
```

またはscriptを直接実行する:

```bash
python scripts/estimate.py "Fix typo in README.md" --json
```

### workspace scanを使う場合（任意）

```bash
python scripts/scan_workspace.py --root . --hint mimu-core/ --json > /tmp/scan.json
python scripts/estimate.py "Refactor routing-policy across plugins" \
  --scan-json /tmp/scan.json --skill-count 8
```

## 構成

```text
User task
  → agent-budget-router (pre-flight estimate)
    → Go / Split / Defer
    → routing-policy Lanes（判定後のdelegation）
        → implementer | analyst-planner | cross-reviewer
```

## Catalog設計

model identityとruntime settingsを分離する:

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

`cursor-grok-4.6-high-fast`のようなsynthetic IDはcatalogに置かない。

## 見積式

```text
Estimated Context
  = Task baseline
  + Expected relevant files
  + Instruction / Skill overhead
  + Re-read / exploration factor
```

探索係数（v1）:

| パターン | 係数 |
|---------|------------|
| single-file edit | ×1.1 – 1.3 |
| known feature area | ×1.3 – 1.6 |
| cross-cutting change | ×1.5 – 2.0 |
| architecture / unknown repo | ×1.8 – 3.0 |

詳細: [references/estimation-rules.md](references/estimation-rules.md)

## 例

| 例 | 判定 | パターン |
|---------|---------|---------|
| [small-fix.md](examples/small-fix.md) | GO | single-file edit |
| [feature-build.md](examples/feature-build.md) | GO | known feature area |
| [large-agent-task.md](examples/large-agent-task.md) | SPLIT_RECOMMENDED | architecture |

## 開発

```bash
python -m pytest tests/
python scripts/estimate.py --task-file examples/small-fix.md
python scripts/compare_runs.py --cursor examples/measurements/cursor-api.json \
  --codex examples/measurements/codex-included-plan.json
```

## 実測コストの比較

同じタスクを両方のrouteで実行した後、実測usage、completion、elapsed time、quality scoreだけを記録し、`compare_runs.py`を実行する。

- Cursor API: 実測した`api_cost_usd`を使う。ない場合は、実測input / cached-input / output tokenと、その時点で適用されたrateを指定する。
- Codex: included plan allowanceか追加creditsかを記録する。included allowanceをzero-dollarのタスク価格として扱わない。
- 両タスクが同程度のqualityで完了し、両方のmarginal USD valueが得られた場合だけroute recommendationを出す。

詳細は[measurement schema](references/measurement-schema.md)と実行可能な[examples](examples/measurements/)を参照する。

## 日常のrouting

通常のinterfaceには`abr.py`を使い、`compare_runs.py`は初回のpaired experimentだけに使う。

```bash
python scripts/abr.py route "repo全体をレビューしてIssue候補を作る"
# 選択した経路で実行し、表示された Preflight ID を使って閉じる
python scripts/abr.py finish <preflight-id> \
  --route codex --completion completed --acceptance satisfied \
  --tests passed --parallel-activity unknown
python scripts/abr.py stats
```

`abr route`は従来どおりタスクを見積もり、`codex app-server`で現在ログイン中のCodexのplan/rate-limit状態を読み、同じtask classの過去実行から中央値を適用する。
plan allowanceが利用できる場合はmedium confidenceで`CODEX`を推奨し、比較可能なCodex実行が3件受け入れられるとconfidenceがhighになる。固定ChatGPT planのタスク単価がzeroとは扱わない。

route結果はpreflight budget gateでもある:

- `NORMAL / AUTO_EXECUTE`: 推定影響が低く、残利用枠が十分で、比較可能な履歴のconfidenceがhigh。
- `CONFIRM / ASK_USER`: 影響が中程度、またはcalibrationが不十分。
- `WARN / SUGGEST_ALTERNATIVE`: 影響が高い、残利用枠が少ない、または現在の利用枠を読めない。

Allowance impactは常にrangeで表示する。帰属可能な履歴がない間は保守的なtask-class priorを`LOW` confidenceとする。帰属可能な実行が3件で`MEDIUM`、6件で`HIGH`になる。

privacy-safeなCodex account snapshot（現在のplan allowanceとglobal token-activity summary）を自動保存するには、work sessionの前後またはautomation hookから次を実行する:

```bash
python scripts/abr.py capture-codex
```

snapshotはglobal account telemetryであり、タスクごとの帰属ではない。routerは無関係な並行usageをタスクへ黙って割り当てない。

`route`はprivacy-safeなbefore snapshotを保存してPreflight IDを表示する。実行後に閉じるとafter snapshotと実測account deltaを取得する:

```bash
python scripts/abr.py finish <preflight-id> \
  --completion completed --acceptance satisfied --elapsed-minutes 13 \
  --tests passed --parallel-activity none
```

タスクに帰属できるdeltaをhigh confidenceとして扱えるのは`--parallel-activity none`だけである。`detected`と`unknown`はaccount-level observationとして残し、次のタスク見積のcalibrationには使わない。

Cursor API cost estimateでは、現在のrateを一度設定する（internal local stateを書き込むが、JSON fileは作成しない）:

```bash
python scripts/abr.py configure \
  --input-rate 4 --cached-input-rate 0.4 --output-rate 20 \
  --cached-input-ratio 0.2
```

実際に使うCursor API modelにその時点で適用されるrateを指定する。routerは変動する価格データを意図的に埋め込まない。

automation hookがpreflightを作成または終了できない場合は、結果だけを記録する代替経路として`record`を使う。同じrunで`record`と`finish`を併用しない。preflightがある場合のcanonical pathは`finish`である。

```bash
python scripts/abr.py record --task-class repository_review \
  --route codex --completion completed --acceptance satisfied \
  --elapsed-minutes 12 --tests passed --lint passed --build passed
```

local historyにはprompt、transcript、source code、secretを保存しない。`quality_score`は任意であり、acceptance criteriaとtest/lint/build結果を主要なperformance signalとする。

## ライセンス

MIT — [LICENSE](LICENSE)を参照
