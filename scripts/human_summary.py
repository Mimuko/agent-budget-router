"""Display-only human summary for Skill v1 ABR results (lookup conversion only)."""

from __future__ import annotations

from typing import Any


REQUIRED_TOP_LEVEL = (
    "schema_version",
    "decision",
    "resolution_status",
    "state",
    "execution_policy",
    "reason",
    "forward",
)

RECOMMENDED_POLICY_LABELS = {
    "DIRECT": "このまま進める",
    "SPLIT": "分割して進める",
    "DEFER": "見送り・再検討",
}

STATE_LABELS = {
    "READY": "実行可能",
    "NEEDS_CONFIRMATION": "承認待ち",
    "BLOCKED": "ブロック中",
}

RESOLUTION_LABELS = {
    "RESOLVED": "外部参照は正常に解決済み",
    "NO_REFERENCE": "外部参照なし",
    "UNRESOLVED": "参照を解決できなかった",
    "PARTIALLY_RESOLVED": "参照は一部のみ取得",
}

REASON_LABELS = {
    "small_task": "タスク規模は小さめ",
    "medium_task": "タスク規模は中程度",
    "cross_cutting": "横断的な変更の兆候あり",
}

TASK_CLASS_LABELS = {
    "small_edit": "タスク種別: 小規模修正",
    "feature_build": "タスク種別: 機能開発",
    "repository_review": "タスク種別: リポジトリレビュー",
    "cross_cutting": "タスク種別: 横断変更",
    "large_refactor": "タスク種別: 大規模リファクタ",
}

RECOMMENDATION_REASON_LABELS = {
    "budget_unavailable": "利用枠情報は未取得",
}


def missing_required_fields(result: dict[str, Any]) -> list[str]:
    """Return missing Skill v1 top-level fields required before display."""
    missing: list[str] = []
    for key in REQUIRED_TOP_LEVEL:
        if key not in result:
            missing.append(key)
    forward = result.get("forward")
    if "forward" in result:
        if not isinstance(forward, dict):
            missing.append("forward.allowed")
        elif "allowed" not in forward or not isinstance(forward.get("allowed"), bool):
            missing.append("forward.allowed")
    return missing


def _provider_suffix(result: dict[str, Any]) -> str:
    """Append provider only when an existing JSON field already names it."""
    for key in ("provider", "reference_provider"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return f"（provider: {value.strip()}）"
    references = result.get("references")
    if isinstance(references, list):
        for item in references:
            if isinstance(item, dict):
                value = item.get("provider")
                if isinstance(value, str) and value.strip():
                    return f"（provider: {value.strip()}）"
    return ""


def _recommended_policy_line(result: dict[str, Any]) -> str:
    if result.get("decision") == "SKIP":
        return "推奨方針: preflight不要"
    preflight = result.get("preflight")
    if isinstance(preflight, dict) and "recommended_policy" in preflight:
        value = preflight["recommended_policy"]
        label = RECOMMENDED_POLICY_LABELS.get(value, value)
        return f"推奨方針: {label}"
    return "推奨方針: 推奨なし（preflight未生成）"


def _state_line(result: dict[str, Any]) -> str:
    state = result["state"]
    return f"現在状態: {STATE_LABELS.get(state, state)}"


def _allowed_line(result: dict[str, Any]) -> str:
    allowed = result["forward"]["allowed"]
    return f"実行可否: {'許可' if allowed else '未許可'}"


def _reason_lines(result: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    status = result.get("resolution_status")
    if isinstance(status, str):
        base = RESOLUTION_LABELS.get(status, status)
        if status in RESOLUTION_LABELS:
            lines.append(f"- {base}{_provider_suffix(result)}")
        else:
            lines.append(f"- {status}")

    reason = result.get("reason")
    if isinstance(reason, str):
        if reason in REASON_LABELS:
            lines.append(f"- {REASON_LABELS[reason]}")
        else:
            lines.append(f"- 理由: {reason}")

    preflight = result.get("preflight")
    if isinstance(preflight, dict):
        task_class = preflight.get("task_class")
        if isinstance(task_class, str):
            lines.append(f"- {TASK_CLASS_LABELS.get(task_class, f'タスク種別: {task_class}')}")
        recommended = preflight.get("recommended_policy")
        if recommended is not None:
            lines.append(f"- Core推奨は {recommended}")
        recommendation_reason = preflight.get("recommendation_reason")
        if isinstance(recommendation_reason, str):
            if recommendation_reason in RECOMMENDATION_REASON_LABELS:
                lines.append(f"- {RECOMMENDATION_REASON_LABELS[recommendation_reason]}")
            else:
                lines.append(f"- 推奨理由: {recommendation_reason}")
    return lines


def _tech_lines(result: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key in ("decision", "resolution_status", "state", "execution_policy"):
        if key in result:
            lines.append(f"- {key}: {result[key]}")
    preflight = result.get("preflight") if isinstance(result.get("preflight"), dict) else {}
    if "recommended_policy" in preflight:
        lines.append(f"- recommended_policy: {preflight['recommended_policy']}")
    forward = result.get("forward")
    if isinstance(forward, dict) and "allowed" in forward:
        lines.append(f"- forward.allowed: {forward['allowed']}")
    if "reason" in result:
        lines.append(f"- reason: {result['reason']}")
    if "recommendation_reason" in preflight:
        lines.append(f"- recommendation_reason: {preflight['recommendation_reason']}")
    if "base_reason" in preflight:
        lines.append(f"- base_reason: {preflight['base_reason']}")
    return lines


def format_human_summary(result: dict[str, Any]) -> str:
    """Convert a contract-valid Skill v1 result dict into the display block.

    Caller must ensure missing_required_fields(result) is empty.
    Does not invent values for missing optional fields.
    """
    parts = [
        "実行前チェック結果",
        "",
        _recommended_policy_line(result),
        _state_line(result),
        _allowed_line(result),
        "",
        "判断理由:",
        *_reason_lines(result),
        "",
        "技術詳細:",
        *_tech_lines(result),
    ]
    return "\n".join(parts) + "\n"
