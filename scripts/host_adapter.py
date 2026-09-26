"""Common Host Adapter PoC governed by docs/architecture/host-adapter-contract.md."""

from __future__ import annotations

import json
import re
import sys
from typing import Any

from abr import route_preflight, should_preflight
from linear_resolver import LinearResolver, Resolution


LINEAR_ISSUE_PATTERN = re.compile(r"(?<![A-Z0-9])(MY-\d+)(?![A-Z0-9])", re.IGNORECASE)
DEFAULT_POLICY = {"input_unavailable": "ask", "reference_unresolved": "ask"}


def policy_result(policy: str, resolution_status: str, reason: str) -> dict[str, Any]:
    if policy == "fail_open":
        return contract_result(
            decision="INPUT_UNAVAILABLE", resolution_status=resolution_status,
            execution_policy="DIRECT", reason=reason,
        )
    if policy == "fail_closed":
        return contract_result(
            decision="INPUT_UNAVAILABLE", resolution_status=resolution_status,
            execution_policy="DEFER", reason=reason,
        )
    return contract_result(
        decision="INPUT_UNAVAILABLE", resolution_status=resolution_status,
        execution_policy="CONFIRM_FIRST", reason=reason,
    )


def contract_result(
    *, decision: str, resolution_status: str, execution_policy: str, reason: str,
    preflight: dict[str, Any] | None = None, confirmation_granted: bool = False,
) -> dict[str, Any]:
    if execution_policy == "DIRECT":
        state, allowed = "READY", True
    elif execution_policy == "CONFIRM_FIRST":
        state, allowed = ("READY", True) if confirmation_granted else ("NEEDS_CONFIRMATION", False)
    elif execution_policy == "SPLIT":
        state, allowed = ("READY", True) if confirmation_granted else ("NEEDS_CONFIRMATION", False)
    elif execution_policy == "DEFER":
        state, allowed = "BLOCKED", False
    else:
        raise ValueError(f"Unknown execution policy: {execution_policy}")
    result = {
        "decision": decision,
        "resolution_status": resolution_status,
        "state": state,
        "execution_policy": execution_policy,
        "reason": reason,
        "preflight": preflight,
        "forward": {"allowed": allowed},
    }
    validate_contract(result, confirmation_granted=confirmation_granted)
    return result


def validate_contract(result: dict[str, Any], *, confirmation_granted: bool = False) -> None:
    state = result.get("state")
    allowed = (result.get("forward") or {}).get("allowed")
    policy = result.get("execution_policy")
    if state not in ("READY", "NEEDS_CONFIRMATION", "BLOCKED"):
        raise ValueError(f"Unknown state: {state}")
    if policy not in ("DIRECT", "CONFIRM_FIRST", "SPLIT", "DEFER"):
        raise ValueError(f"Unknown execution policy: {policy}")
    if not isinstance(allowed, bool):
        raise ValueError("forward.allowed must be boolean")
    if state == "READY" and allowed is not True:
        raise ValueError("READY requires forward.allowed=true")
    if state in ("NEEDS_CONFIRMATION", "BLOCKED") and allowed is not False:
        raise ValueError(f"{state} requires forward.allowed=false")
    if policy == "CONFIRM_FIRST" and not confirmation_granted and state != "NEEDS_CONFIRMATION":
        raise ValueError("Unapproved CONFIRM_FIRST requires NEEDS_CONFIRMATION")
    if policy == "SPLIT" and not confirmation_granted and state != "NEEDS_CONFIRMATION":
        raise ValueError("Unplanned SPLIT requires NEEDS_CONFIRMATION")
    if policy == "DEFER" and state != "BLOCKED":
        raise ValueError("DEFER requires BLOCKED")


def approve(result: dict[str, Any]) -> dict[str, Any]:
    """Pure transition helper; persistence and UI are intentionally out of scope."""
    if result.get("state") != "NEEDS_CONFIRMATION":
        raise ValueError("Only NEEDS_CONFIRMATION can be approved")
    return contract_result(
        decision=result["decision"],
        resolution_status=result["resolution_status"],
        execution_policy=result["execution_policy"],
        reason=result["reason"],
        preflight=result.get("preflight"),
        confirmation_granted=True,
    )


def resolve_context(prompt: str, linear_resolver: LinearResolver) -> Resolution | None:
    match = LINEAR_ISSUE_PATTERN.search(prompt)
    return linear_resolver.resolve(match.group(1).upper()) if match else None


def evaluate_request(
    request: dict[str, Any], *, linear_resolver: LinearResolver | None = None,
) -> dict[str, Any]:
    policy = {**DEFAULT_POLICY, **(request.get("policy") or {})}
    prompt = request.get("prompt")
    if not request.get("prompt_available") or not isinstance(prompt, str) or not prompt.strip():
        return policy_result(policy["input_unavailable"], "NO_REFERENCE", "input_unavailable")

    resolution = resolve_context(prompt, linear_resolver or LinearResolver())
    if resolution and resolution.reference["resolution_status"] == "UNRESOLVED":
        return policy_result(policy["reference_unresolved"], "UNRESOLVED", "unresolved_reference")

    resolution_status = resolution.reference["resolution_status"] if resolution else "NO_REFERENCE"
    task_context = resolution.task_context if resolution else None
    decision = should_preflight(prompt, task_context)
    if decision["decision"] == "INPUT_UNAVAILABLE":
        return policy_result(policy["input_unavailable"], resolution_status, decision["reason"])
    if decision["decision"] == "SKIP":
        return contract_result(
            decision="SKIP", resolution_status=resolution_status,
            execution_policy="DIRECT", reason=decision["reason"],
        )

    preflight = route_preflight(prompt, task_context)
    return contract_result(
        decision="PREFLIGHT", resolution_status=resolution_status,
        execution_policy=preflight["execution_policy"], reason=decision["reason"],
        preflight=preflight,
    )


def main() -> int:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("request must be a JSON object")
        print(json.dumps(evaluate_request(request), ensure_ascii=False))
        return 0
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"host-adapter: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
