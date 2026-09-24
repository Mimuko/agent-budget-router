"""Skill v1 orchestration over provider-neutral Core inputs and outputs."""

from __future__ import annotations

import json
import sys
from typing import Any, Protocol

from abr_core import estimate_task, route, should_preflight
from reference_resolver import ReferenceResolver


DEFAULT_POLICY = {"input_unavailable": "ask", "reference_unresolved": "ask"}
POLICY_VALUES = frozenset({"ask", "fail_open", "fail_closed"})


class BudgetCostEstimator(Protocol):
    """External boundary; returns a comparable normalized snapshot or None."""

    def estimate(self, task_estimate: dict[str, Any]) -> dict[str, Any] | None: ...


def _result(
    decision: str, resolution_status: str, reason: str, execution_policy: str,
    preflight: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if execution_policy == "DIRECT":
        state, allowed = "READY", True
    elif execution_policy in ("CONFIRM_FIRST", "SPLIT"):
        state, allowed = "NEEDS_CONFIRMATION", False
    elif execution_policy == "DEFER":
        state, allowed = "BLOCKED", False
    else:
        raise ValueError("invalid execution_policy")
    return {
        "schema_version": "skill-v1",
        "decision": decision,
        "resolution_status": resolution_status,
        "state": state,
        "execution_policy": execution_policy,
        "reason": reason,
        "preflight": preflight,
        "forward": {"allowed": allowed},
    }


def _policy_result(policy: str, resolution_status: str, reason: str) -> dict[str, Any]:
    execution = {"fail_open": "DIRECT", "ask": "CONFIRM_FIRST", "fail_closed": "DEFER"}[policy]
    return _result("INPUT_UNAVAILABLE", resolution_status, reason, execution)


def evaluate_request(
    request: dict[str, Any], *, resolver: ReferenceResolver | None = None,
    budget_estimator: BudgetCostEstimator | None = None,
) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise ValueError("request must be an object")
    supplied_policy = request.get("policy") or {}
    if not isinstance(supplied_policy, dict):
        raise ValueError("policy must be an object")
    policy = {**DEFAULT_POLICY, **supplied_policy}
    if any(policy[key] not in POLICY_VALUES for key in DEFAULT_POLICY):
        raise ValueError("invalid policy value")
    prompt = request.get("prompt")
    if not request.get("prompt_available") or not isinstance(prompt, str) or not prompt.strip():
        return _policy_result(policy["input_unavailable"], "NO_REFERENCE", "input_unavailable")

    resolution = (resolver or ReferenceResolver()).resolve(prompt)
    status = resolution.resolution_status
    if status in ("UNRESOLVED", "PARTIALLY_RESOLVED"):
        return _policy_result(policy["reference_unresolved"], status, "unresolved_reference")

    decision = should_preflight(prompt, resolution.task_context)
    if decision["decision"] == "INPUT_UNAVAILABLE":
        return _policy_result(policy["input_unavailable"], status, decision["reason"])
    if decision["decision"] == "SKIP":
        return _result("SKIP", status, decision["reason"], "DIRECT")

    task_estimate = estimate_task(prompt, resolution.task_context)
    budget_context = budget_estimator.estimate(task_estimate) if budget_estimator else None
    preflight = route(task_estimate, budget_context)
    recommended = preflight["recommended_policy"]
    # Preserve the existing preflight confirmation gate for a DIRECT recommendation.
    execution = "CONFIRM_FIRST" if recommended == "DIRECT" else recommended
    return _result("PREFLIGHT", status, decision["reason"], execution, preflight)


def main() -> int:
    try:
        request = json.load(sys.stdin)
        print(json.dumps(evaluate_request(request), ensure_ascii=False))
        return 0
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"skill-orchestrator: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
