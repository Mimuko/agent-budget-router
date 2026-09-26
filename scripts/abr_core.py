"""Host-independent Skill v1 task sizing and budget recommendation."""

from __future__ import annotations

import math
import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from estimate import estimate_task_size


PREFLIGHT_SIGNALS = (
    "横断", "複数", "全体", "リファクタ", "設計", "architecture", "integration",
    "migrate", "migration", "plugin", "skill", "モデル", "検証", "連携",
)
ISSUE_PATTERN = re.compile(r"(?<![A-Z0-9])[A-Z][A-Z0-9]+-\d+(?![A-Z0-9])", re.IGNORECASE)
TASK_CLASSES = frozenset({
    "small_edit", "feature_build", "repository_review", "cross_cutting", "large_refactor",
})
POLICIES = {"DIRECT": 0, "SPLIT": 1, "DEFER": 2}
LEGACY_VERDICTS = {"GO": "DIRECT", "SPLIT_RECOMMENDED": "SPLIT", "DEFER": "DEFER"}
RFC3339_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?"
    r"(?:[Zz]|[+-](?:[01]\d|2[0-3]):[0-5]\d)$"
)


def _validate_context(task_context: dict[str, Any] | None) -> None:
    if task_context is None:
        return
    if not isinstance(task_context, dict):
        raise ValueError("task_context must be an object")
    for key in ("title", "summary"):
        if key in task_context and not isinstance(task_context[key], str):
            raise ValueError(f"task_context.{key} must be a string")
    for key in ("acceptance_criteria", "path_hints", "related_links"):
        if key in task_context and (
            not isinstance(task_context[key], list)
            or any(not isinstance(item, str) for item in task_context[key])
        ):
            raise ValueError(f"task_context.{key} must be a list of strings")


def task_class(task: str, exploration: str) -> str:
    lower = task.lower()
    if any(word in lower for word in ("repo全体", "repository", "全体をレビュー", "issue候補", "audit")):
        return "repository_review"
    if exploration == "single-file edit":
        return "small_edit"
    if exploration == "known feature area":
        return "feature_build"
    if exploration == "cross-cutting change":
        return "cross_cutting"
    return "large_refactor"


def core_task_text(prompt: str, task_context: dict[str, Any] | None = None) -> str:
    _validate_context(task_context)
    parts = [prompt]
    if task_context:
        for key in ("title", "summary"):
            if task_context.get(key):
                parts.append(task_context[key])
        parts.extend(task_context.get("acceptance_criteria", []))
    return "\n".join(part for part in parts if part).strip()


def should_preflight(prompt: str, task_context: dict[str, Any] | None = None) -> dict[str, str]:
    """Cheap decision; does not estimate, fetch a budget, or inspect history."""
    _validate_context(task_context)
    if not isinstance(prompt, str) or not prompt.strip():
        return {"decision": "INPUT_UNAVAILABLE", "reason": "input_unavailable"}
    text = core_task_text(prompt, task_context)
    lower = text.lower()
    if task_context is not None or ISSUE_PATTERN.search(text) or any(signal in lower for signal in PREFLIGHT_SIGNALS):
        reason = "cross_cutting" if any(signal in lower for signal in PREFLIGHT_SIGNALS) else "medium_task"
        return {"decision": "PREFLIGHT", "reason": reason}
    return {"decision": "SKIP", "reason": "small_task"}


def estimate_task(prompt: str, task_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Produce one reusable, budget-independent task estimate."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt is required")
    text = core_task_text(prompt, task_context)
    path_hints = task_context.get("path_hints") if task_context else None
    result = estimate_task_size(text, path_hints=path_hints or None)
    kind = task_class(text, result["exploration_pattern"])
    try:
        base = LEGACY_VERDICTS[result["verdict"]]
    except KeyError as exc:
        raise ValueError("unknown legacy estimate verdict") from exc
    task_estimate = {
        "task_class": kind,
        "estimated_context": dict(result["estimated_context"]),
        "estimated_generation": dict(result["estimated_generation"]),
        "base_recommendation": base,
        "base_reason": kind,
    }
    validate_task_estimate(task_estimate)
    return task_estimate


def _validate_range(value: Any, name: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    low, high = value.get("min"), value.get("max")
    if any(isinstance(number, bool) or not isinstance(number, int) for number in (low, high)):
        raise ValueError(f"{name} bounds must be integers")
    if low < 0 or high < low:
        raise ValueError(f"{name} requires 0 <= min <= max")


def validate_task_estimate(task_estimate: Any) -> None:
    if not isinstance(task_estimate, dict):
        raise ValueError("task_estimate must be an object")
    if task_estimate.get("task_class") not in TASK_CLASSES:
        raise ValueError("invalid task_class")
    _validate_range(task_estimate.get("estimated_context"), "estimated_context")
    _validate_range(task_estimate.get("estimated_generation"), "estimated_generation")
    if task_estimate.get("base_recommendation") not in POLICIES:
        raise ValueError("invalid base_recommendation")
    if not isinstance(task_estimate.get("base_reason"), str) or not task_estimate["base_reason"].strip():
        raise ValueError("base_reason must be a non-empty string")


def _ratio(value: Any, name: str, *, max_value: float | None = None) -> Decimal:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or (isinstance(value, float) and not math.isfinite(value))):
        raise ValueError(f"{name} must be a finite number")
    if value < 0 or (max_value is not None and value > max_value):
        raise ValueError(f"{name} is out of range")
    return Decimal(str(value))


def validate_budget_context(budget_context: Any) -> tuple[Decimal, Decimal]:
    if not isinstance(budget_context, dict):
        raise ValueError("budget_context must be an object")
    remaining = _ratio(budget_context.get("remaining_ratio"), "remaining_ratio", max_value=1)
    task = _ratio(budget_context.get("estimated_task_ratio"), "estimated_task_ratio")
    snapshot_at = budget_context.get("snapshot_at")
    if not isinstance(snapshot_at, str) or not RFC3339_TIMESTAMP.fullmatch(snapshot_at):
        raise ValueError("snapshot_at must be an RFC 3339 timestamp with UTC offset")
    try:
        datetime.fromisoformat(snapshot_at.upper().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("snapshot_at must be an RFC 3339 timestamp with UTC offset") from exc
    if not isinstance(budget_context.get("scope"), str) or not budget_context["scope"].strip():
        raise ValueError("scope must be a non-empty string")
    return remaining, task


def route(task_estimate: dict[str, Any], budget_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge a precomputed task recommendation with an optional budget ratio."""
    validate_task_estimate(task_estimate)
    base = task_estimate["base_recommendation"]
    recommended = base
    reason = "budget_unavailable" if budget_context is None else task_estimate["base_reason"]
    if budget_context is not None:
        remaining, task = validate_budget_context(budget_context)
        if remaining == 0:
            budget, budget_reason = "DEFER", "budget_exhausted"
        elif task <= remaining * Decimal("0.50"):
            budget, budget_reason = "DIRECT", "budget_roomy"
        elif task <= remaining:
            budget, budget_reason = "SPLIT", "budget_limited"
        else:
            budget, budget_reason = "DEFER", "budget_exceeded"
        if POLICIES[budget] > POLICIES[base]:
            recommended, reason = budget, budget_reason
    return {
        "task_class": task_estimate["task_class"],
        "estimated_context": dict(task_estimate["estimated_context"]),
        "estimated_generation": dict(task_estimate["estimated_generation"]),
        "base_recommendation": base,
        "base_reason": task_estimate["base_reason"],
        "recommended_policy": recommended,
        "recommendation_reason": reason,
    }
