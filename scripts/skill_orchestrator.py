"""Skill v1 orchestration over provider-neutral Core inputs and outputs."""

from __future__ import annotations

import json
import hashlib
import os
import sys
import unicodedata
from typing import Any, Protocol

from abr_core import estimate_task, route, should_preflight
from linear_backend import OrcaLinearBackend
from linear_resolver import LinearResolver
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
    return _evaluate_request(request, resolver=resolver, budget_estimator=budget_estimator)[0]


def _evaluate_request(
    request: dict[str, Any], *, resolver: ReferenceResolver | None = None,
    budget_estimator: BudgetCostEstimator | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
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
        return _policy_result(policy["input_unavailable"], "NO_REFERENCE", "input_unavailable"), None

    resolution = (resolver or ReferenceResolver()).resolve(prompt)
    status = resolution.resolution_status
    if status in ("UNRESOLVED", "PARTIALLY_RESOLVED"):
        return _policy_result(policy["reference_unresolved"], status, "unresolved_reference"), resolution.source_identity

    decision = should_preflight(prompt, resolution.task_context)
    if decision["decision"] == "INPUT_UNAVAILABLE":
        return _policy_result(policy["input_unavailable"], status, decision["reason"]), resolution.source_identity
    if decision["decision"] == "SKIP":
        return _result("SKIP", status, decision["reason"], "DIRECT"), resolution.source_identity

    task_estimate = estimate_task(prompt, resolution.task_context)
    budget_context = budget_estimator.estimate(task_estimate) if budget_estimator else None
    preflight = route(task_estimate, budget_context)
    recommended = preflight["recommended_policy"]
    # The Skill's user gate is independent of Core's recommended host execution policy.
    # Keep SPLIT in preflight; the caller owns any plan or task decomposition after approval.
    execution = "DEFER" if recommended == "DEFER" else "CONFIRM_FIRST"
    return _result("PREFLIGHT", status, decision["reason"], execution, preflight), resolution.source_identity


def _approval_fingerprint(request: dict[str, Any], result: dict[str, Any], source_identity: dict[str, Any] | None) -> str:
    prompt = request.get("prompt")
    normalized_prompt = ""
    if isinstance(prompt, str):
        normalized_prompt = unicodedata.normalize("NFC", prompt.replace("\r\n", "\n").replace("\r", "\n"))
    payload = {
        "schema_version": "skill-v1",
        "prompt": normalized_prompt,
        "workspace_scope": request.get("workspace_scope"),
        "repository_scope": request.get("repository_scope"),
        "source_identity": source_identity,
        "decision": {
            key: result.get(key) for key in (
                "decision", "resolution_status", "state", "execution_policy", "reason", "preflight",
            )
        },
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SkillWorkflow:
    """Single-process approval handoff with fresh resolution and one READY consume."""

    def __init__(
        self, *, resolver: ReferenceResolver | None = None,
        budget_estimator: BudgetCostEstimator | None = None,
    ) -> None:
        self._resolver = resolver
        self._budget_estimator = budget_estimator
        self._pending_fingerprint: str | None = None
        self._pending_result: dict[str, Any] | None = None
        self._consumed = False

    def start(self, request: dict[str, Any]) -> dict[str, Any]:
        if self._pending_result is not None or self._consumed:
            raise ValueError("workflow has already started")
        result, source_identity = _evaluate_request(
            request, resolver=self._resolver, budget_estimator=self._budget_estimator,
        )
        if result["state"] == "NEEDS_CONFIRMATION":
            self._pending_fingerprint = _approval_fingerprint(request, result, source_identity)
            self._pending_result = result
        return result

    def resume(self, request: dict[str, Any], *, approved: bool) -> dict[str, Any]:
        if self._pending_result is None or self._consumed:
            raise ValueError("workflow has no pending confirmation")
        if not isinstance(approved, bool):
            raise ValueError("approved must be a boolean")
        if not approved:
            self._consumed = True
            return _result(
                "PREFLIGHT", self._pending_result["resolution_status"], "approval_rejected", "DEFER",
                self._pending_result.get("preflight"),
            )
        # Resolve and run the Core again; approval applies only if the complete decision still matches.
        current, source_identity = _evaluate_request(
            request, resolver=self._resolver, budget_estimator=self._budget_estimator,
        )
        current_fingerprint = _approval_fingerprint(request, current, source_identity)
        self._consumed = True
        if current_fingerprint != self._pending_fingerprint:
            return current
        if current["execution_policy"] == "CONFIRM_FIRST" and current["state"] == "NEEDS_CONFIRMATION":
            current["state"] = "READY"
            current["forward"] = {"allowed": True}
        return current


def _make_resolver() -> ReferenceResolver | None:
    if os.environ.get("ABR_LINEAR_BACKEND", "").lower() == "orca":
        return ReferenceResolver({"linear": LinearResolver(backend=OrcaLinearBackend())})
    return None


def run_session() -> int:
    """JSON-lines caller protocol; the caller owns confirmation UI and returns its choice."""
    workflow = SkillWorkflow(resolver=_make_resolver())
    started = False
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                raise ValueError("message must be an object")
            if message.get("action") == "start" and not started:
                result = workflow.start(message.get("request"))
                started = True
            elif message.get("action") == "resume" and started:
                result = workflow.resume(message.get("request"), approved=message.get("approved") is True)
            else:
                raise ValueError("expected one start followed by at most one resume")
            print(json.dumps(result, ensure_ascii=False), flush=True)
        except (ValueError, json.JSONDecodeError) as exc:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False), flush=True)
            return 2
    return 0


def main() -> int:
    if "--session" in sys.argv[1:]:
        return run_session()
    try:
        request = json.load(sys.stdin)
        print(json.dumps(evaluate_request(request, resolver=_make_resolver()), ensure_ascii=False))
        return 0
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"skill-orchestrator: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
