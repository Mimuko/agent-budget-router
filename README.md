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

- [mimu-core](https://github.com/Mimuko/agent-plugins) routing-policy §7 (optional)
- Cursor subagents with pinned `model` + `effort` / `speed` in catalog

## Quick start

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
python scripts/abr.py stats
```

`abr route` estimates the task as before, reads the currently logged-in Codex
plan/rate-limit state through `codex app-server`, and applies median facts from
prior runs of the same task class. It recommends `CODEX` at medium confidence
when plan allowance is available; confidence becomes high after three accepted
comparable Codex runs. It does not claim that a fixed ChatGPT plan has a zero
per-task price.

To automatically retain a privacy-safe Codex account snapshot (current plan
allowance and global token-activity summary), run this before/after a work
session or from an automation hook:

```bash
python scripts/abr.py capture-codex
```

The snapshot is global account telemetry, not a per-task attribution. The
router never silently assigns unrelated concurrent usage to a task.

For Cursor API cost estimates, configure the current rates once (this writes
internal local state; you do not create a JSON file):

```bash
python scripts/abr.py configure \
  --input-rate 4 --cached-input-rate 0.4 --output-rate 20 \
  --cached-input-ratio 0.2
```

Use the rates applicable to the actual Cursor API model at the time; the
router intentionally does not embed volatile price data.

After a run, record outcome facts rather than a hand-authored comparison JSON:

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
