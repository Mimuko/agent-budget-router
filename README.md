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
- Compares observed Cursor → OpenAI API and Codex runs without inventing a per-task price for included plan allowance

## What it does NOT do

- Switch your chat model for you
- Guarantee billing accuracy
- Replace your team's routing policy

## Works well with

- [mimu-core](https://github.com/Mimuko/agent-plugins) routing-policy §7（役割）/ §8（Cursor Adapter, optional）
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

## License

MIT — see [LICENSE](LICENSE)
