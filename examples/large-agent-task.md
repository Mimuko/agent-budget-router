# Example: large agent task

Implement a new AgentPlugin from scratch: scaffold, SKILL.md, catalog, scripts,
examples, README, and cross-plugin routing-policy integration across the monorepo.
First-time architecture work, multiple directories, high exploration risk.

## Expected output

With `--budget-tight`:

- **Verdict:** DEFER
- **Complexity:** HIGH or CRITICAL
- **Pattern:** architecture / unknown repo

Without `--budget-tight`:

- **Verdict:** SPLIT_RECOMMENDED
- **Phases:** Planning → analyst-planner, Execution → implementer, Review → cross-reviewer

## Run

```bash
python scripts/estimate.py \
  "Implement agent-budget-router as a standalone OSS skill with catalog, estimate.py, examples, and mimu-core routing-policy link. Cross-cutting Plugin work." \
  --skill-count 10 \
  --budget-tight
```

## Why SPLIT

High exploration multiplier (×1.8–3.0) from re-read / subagent / test-failure loops.
Running entirely on a frontier model would burn budget before quality is visible.
