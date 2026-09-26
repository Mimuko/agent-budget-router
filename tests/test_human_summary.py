"""Unit tests for display-only ABR human summary formatter."""

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from human_summary import format_human_summary, missing_required_fields  # noqa: E402


def case_a_skip() -> dict:
    return {
        "schema_version": "skill-v1",
        "decision": "SKIP",
        "resolution_status": "NO_REFERENCE",
        "state": "READY",
        "execution_policy": "DIRECT",
        "reason": "small_task",
        "preflight": None,
        "forward": {"allowed": True},
    }


def case_b_confirm() -> dict:
    return {
        "schema_version": "skill-v1",
        "decision": "PREFLIGHT",
        "resolution_status": "RESOLVED",
        "state": "NEEDS_CONFIRMATION",
        "execution_policy": "CONFIRM_FIRST",
        "reason": "medium_task",
        "preflight": {
            "recommended_policy": "SPLIT",
            "task_class": "feature_build",
            "base_reason": "feature_build",
            "recommendation_reason": "budget_unavailable",
        },
        "forward": {"allowed": False},
    }


def test_case_a_skip_recommended_policy_is_preflight_unnecessary():
    text = format_human_summary(case_a_skip())
    assert text.startswith("実行前チェック結果\n")
    assert "推奨方針: preflight不要" in text
    assert "現在状態: 実行可能" in text
    assert "実行可否: 許可" in text
    assert "Linear" not in text


def test_case_b_maps_policies_without_confusing_execution_and_recommended():
    text = format_human_summary(case_b_confirm())
    assert "推奨方針: 分割して進める" in text
    assert "現在状態: 承認待ち" in text
    assert "実行可否: 未許可" in text
    assert "外部参照は正常に解決済み" in text
    assert "Linear Issue" not in text
    assert "タスク規模は中程度" in text
    assert "タスク種別: 機能開発" in text
    assert "Core推奨は SPLIT" in text
    assert "利用枠情報は未取得" in text
    assert "- execution_policy: CONFIRM_FIRST" in text
    assert "- recommended_policy: SPLIT" in text
    assert "- base_reason: feature_build" in text


def test_unknown_task_class_keeps_raw_value():
    result = case_b_confirm()
    result["preflight"]["task_class"] = "custom_kind"
    text = format_human_summary(result)
    assert "タスク種別: custom_kind" in text


def test_provider_suffix_only_when_field_present():
    result = case_b_confirm()
    assert "provider:" not in format_human_summary(result)
    result["provider"] = "linear"
    assert "（provider: linear）" in format_human_summary(result)


def test_missing_required_fields_lists_gaps():
    assert missing_required_fields(case_a_skip()) == []
    broken = {"schema_version": "skill-v1", "decision": "SKIP"}
    missing = missing_required_fields(broken)
    assert "state" in missing
    assert "forward" in missing
    no_allowed = {**case_a_skip(), "forward": {}}
    assert "forward.allowed" in missing_required_fields(no_allowed)
    null_forward = {**case_a_skip(), "forward": None}
    assert "forward.allowed" in missing_required_fields(null_forward)
