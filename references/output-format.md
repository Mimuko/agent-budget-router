# Output format

Agent Budget Router が返すレポート形式。Skill はこのテンプレに従う。

## 人間向けレポート

```text
## Agent Budget Report

Verdict: GO | SPLIT_RECOMMENDED | DEFER
Task complexity: LOW | MEDIUM | HIGH | CRITICAL
Exploration pattern: single-file edit | known feature area | cross-cutting change | architecture / unknown repo
Confidence: LOW | MEDIUM | HIGH

Estimated context:     {min}k – {max}k tokens
  (expected agent context — not full repository size)
Estimated generation:   {min}k –  {max}k tokens
Exploration factor:    ×{min}–{max} ({pattern label})
Agent overhead:        LOW | MEDIUM | HIGH

Recommended phases:
  Planning   → {lane} ({model display}, {params})
  Execution  → {lane} ({model display}, {params})
  Review     → {lane} ({model display}, {params})

Budget risk:
  {risk lines}

Why this exists:
  I gave a large AgentPlugin implementation task to a high-end agent model
  and burned through the entire usage allowance before I could tell
  whether the model was actually better.

Next actions:
  1. {action}
  2. {action}
  3. {action}
```

## 機械可読 JSON

`scripts/estimate.py --json` の出力スキーマ:

```json
{
  "verdict": "GO | SPLIT_RECOMMENDED | DEFER",
  "complexity": "LOW | MEDIUM | HIGH | CRITICAL",
  "exploration_pattern": "single-file edit | known feature area | cross-cutting change | architecture / unknown repo",
  "confidence": "LOW | MEDIUM | HIGH",
  "estimated_context": { "min": 0, "max": 0 },
  "estimated_generation": { "min": 0, "max": 0 },
  "exploration_factor": { "min": 1.0, "max": 1.0, "label": "..." },
  "agent_overhead": "LOW | MEDIUM | HIGH",
  "recommended_phases": [
    {
      "phase": "Planning | Execution | Review",
      "lane": "analyst-planner",
      "model": "cursor-grok-4.6",
      "effort": "high",
      "speed": "standard",
      "resolved": "cursor-grok-4.6 (effort=high, speed=standard)"
    }
  ],
  "budget_risk": ["..."],
  "next_actions": ["..."],
  "signals": {
    "complexity_score": 0,
    "task_baseline": { "min": 0, "max": 0 },
    "relevant_files": { "min": 0, "max": 0 },
    "skill_overhead": { "min": 0, "max": 0 }
  }
}
```

## Verdict 表示ルール

- **GO**: 緑系の判断材料。単一 Lane 投入可の見込み
- **SPLIT_RECOMMENDED**: 黄系。フェーズ分割を明示
- **DEFER**: 赤系。人間判断または調査先行

## Budget risk 例文

- `High-cost route if run entirely on frontier model`
- `→ 設計フェーズのみ High effort、実装は Composer に分割推奨`
- `Skill/Plugin overhead is significant — scope active rules before agent run`
- `Budget constraint flagged — consider deferring or splitting`
