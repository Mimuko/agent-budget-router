# Host shim contract (PoC)

Verification status: Orca, Cursor, and Codex execution are verified in the MY-215 worktree.

The intended common interface routes each host to `scripts/skill_orchestrator.py` and its
`skill-v1` JSON result. A shim only maps the host's explicit Skill invocation, confirmation
UI, and result display to this protocol. It must not interpret a result as permission when
`forward.allowed` is false.

## Invocation mapping

| Host | Explicit invocation | Shim responsibility |
|:--|:--|:--|
| Cursor | `/agent-budget-router <task>` | Project Skill at `.cursor/skills/agent-budget-router/SKILL.md` uses the Cursor adapter and preserves a confirmation session across chat turns. |
| Codex | `$agent-budget-router <task>` | Project Skill at `.agents/skills/agent-budget-router/SKILL.md` uses the Codex adapter and preserves a confirmation session across turns. |
| Orca | Explicitly invoke the configured `agent-budget-router` Skill | Orca CLI session verified; no GUI Skill surface claimed. |

The shared package is logical. Each host may install it using its own Skill discovery format.
No Hook, automatic invocation, child-agent launch, or target-task implementation is part of
this shim contract.

## Confirmation session

Start one long-lived Orchestrator process from `agent-budget-router/`:

```text
python scripts/skill_orchestrator.py --session
```

Send one JSON line and read one JSON result:

```json
{"action":"start","request":{"prompt":"READMEの誤字修正して","prompt_available":true}}
```

For a confirmation-required task, keep the same process and let the host present its normal
confirmation UI. After approval, send the original request again with the user's decision:

```json
{"action":"resume","request":{"prompt":"MY-172を実装して","prompt_available":true},"approved":true}
```

The Orchestrator re-resolves references and reruns Core before returning a result. The host
forwards the task only for `state: READY` and `forward.allowed: true`. A changed prompt,
workspace, repository, Linear source, or Core decision invalidates the approval. Each session
accepts at most one resume; the process keeps only in-memory confirmation state.

## Local Linear PoC

The default Core has no implicit Linear connection. In a development checkout with Orca
Linear access, opt in for the PoC process:

```powershell
$env:ABR_LINEAR_BACKEND = "orca"
python scripts/skill_orchestrator.py --session
```

This reads through `orca linear issue <id> --full --json`. It is a development fallback only;
the production Linear backend remains unselected. Without the explicit setting, referenced
issues are returned as unresolved and the default `ask` policy prevents forwarding.

## Fixed cases

| Request | Expected common result |
|:--|:--|
| `READMEの誤字修正して` | `NO_REFERENCE`, `SKIP`, `READY`, `DIRECT`, allowed `true` |
| `MY-172を実装して` with local Orca backend | `RESOLVED`, `PREFLIGHT`, `NEEDS_CONFIRMATION`, `CONFIRM_FIRST`, allowed `false` |
| Same request after approval and unchanged Linear source | `READY`, allowed `true`, exactly once |

The common code and I/O contract define one result vocabulary. The Orca, Cursor, and Codex
runtime checks covered Case A, Case B, approval to READY, and duplicate approval rejection.
