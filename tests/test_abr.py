"""Tests for the daily abr route / stats CLI."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from abr import (  # noqa: E402
    append_snapshot,
    budget_gate,
    build_parser,
    cursor_estimated_cost,
    decide_route,
    estimate_allowance_impact,
    route_stats,
    task_class,
)


def test_configure_uses_cli_options_not_a_user_authored_json_file():
    args = build_parser().parse_args([
        "configure", "--input-rate", "2", "--cached-input-rate", "0.2", "--output-rate", "10",
    ])
    assert args.input_rate == 2
    assert args.cached_input_ratio == 0


def test_capture_snapshot_is_kept_separate_from_task_runs(tmp_path):
    path = append_snapshot(tmp_path, {"available": True, "used_percent": 25})
    assert path.name == "usage-snapshots.jsonl"
    assert '"used_percent":25' in path.read_text(encoding="utf-8")


def test_task_class_uses_repository_review_before_generic_architecture():
    assert task_class("repo全体をレビューしてIssue候補を作る", "architecture / unknown repo") == "repository_review"


def test_cursor_cost_uses_configured_rates_without_embedded_prices():
    result = {
        "estimated_context": {"max": 100_000},
        "estimated_generation": {"max": 10_000},
    }
    config = {"cursor_api_rates_usd_per_mtok": {"input": 2, "cached_input": 0.2, "output": 10}, "cursor_cached_input_ratio": 0.2}
    assert cursor_estimated_cost(result, config) == 0.264


def test_route_prefers_available_codex_plan_at_medium_confidence_without_history():
    empty = {"runs": 0, "acceptance_rate": None}
    recommendation, confidence, _ = decide_route(0.4, {"available": True}, empty, empty)
    assert (recommendation, confidence) == ("CODEX", "MEDIUM")


def test_stats_uses_acceptance_signals_not_subjective_quality():
    runs = [
        {"task_class": "small_edit", "route": "codex", "completion": "completed", "acceptance": "satisfied", "elapsed_minutes": 10, "credit_units": 2},
        {"task_class": "small_edit", "route": "codex", "completion": "completed", "acceptance": "unsatisfied", "elapsed_minutes": 14, "credit_units": 4},
    ]
    stats = route_stats(runs, "small_edit", "codex")
    assert stats["acceptance_rate"] == 0.5
    assert stats["median_elapsed_minutes"] == 12
    assert stats["accepted_without_revision"] == 1


def test_allowance_impact_starts_as_low_confidence_range():
    impact = estimate_allowance_impact("repository_review", {"attributable_deltas": []})
    assert impact == {
        "min_percent_points": 3.0,
        "max_percent_points": 5.0,
        "confidence": "LOW",
        "sample_count": 0,
        "source": "bootstrap_task_class_prior",
    }


def test_allowance_impact_becomes_high_confidence_after_six_attributable_runs():
    impact = estimate_allowance_impact(
        "repository_review", {"attributable_deltas": [3, 4, 3, 5, 4, 4]}
    )
    assert impact["confidence"] == "HIGH"
    assert (impact["min_percent_points"], impact["max_percent_points"]) == (3.0, 5.0)


def test_budget_gate_levels():
    normal = budget_gate(
        {"max_percent_points": 2, "confidence": "HIGH"}, {"used_percent": 20}
    )
    confirm = budget_gate(
        {"max_percent_points": 4, "confidence": "MEDIUM"}, {"used_percent": 37}
    )
    warn = budget_gate(
        {"max_percent_points": 14, "confidence": "MEDIUM"}, {"used_percent": 81}
    )
    assert normal["level"] == "NORMAL"
    assert confirm["level"] == "CONFIRM"
    assert warn["level"] == "WARN"


def test_budget_gate_warns_when_live_allowance_is_missing():
    gate = budget_gate({"max_percent_points": 2, "confidence": "HIGH"}, None)
    assert gate == {
        "level": "WARN",
        "action": "SUGGEST_ALTERNATIVE",
        "reason": "Live Codex allowance is unavailable",
    }
