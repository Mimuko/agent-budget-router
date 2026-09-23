"""Tests for the daily abr route / stats CLI."""

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from abr import (  # noqa: E402
    append_snapshot,
    append_run,
    budget_gate,
    build_parser,
    command_finish,
    command_route,
    cursor_estimated_cost,
    decide_route,
    estimate_allowance_impact,
    route_stats,
    task_class,
)


def finish_args(tmp_path, preflight_id="preflight-1"):
    return build_parser().parse_args([
        "--state-dir", str(tmp_path), "finish", preflight_id,
        "--completion", "completed", "--acceptance", "satisfied",
    ])


def test_configure_uses_cli_options_not_a_user_authored_json_file():
    args = build_parser().parse_args([
        "configure", "--input-rate", "2", "--cached-input-rate", "0.2", "--output-rate", "10",
    ])
    assert args.input_rate == 2
    assert args.cached_input_ratio == 0


def test_route_accepts_standard_prompt_from_stdin():
    args = build_parser().parse_args(["route", "--stdin", "--json", "--no-codex-probe"])
    assert args.task is None
    assert args.stdin is True


def test_route_accepts_standard_prompt_from_task_file(tmp_path):
    task_file = tmp_path / "prompt.txt"
    task_file.write_text("  Fix the routing policy.\n", encoding="utf-8")
    args = build_parser().parse_args(["route", "--task-file", str(task_file), "--json", "--no-codex-probe"])
    assert args.task_file == task_file


def test_route_task_sources_are_mutually_exclusive(tmp_path):
    task_file = tmp_path / "prompt.txt"
    task_file.write_text("task", encoding="utf-8")
    args = build_parser().parse_args(["route", "inline", "--task-file", str(task_file)])
    from abr import read_route_task
    try:
        read_route_task(args)
    except ValueError as exc:
        assert "exactly one task source" in str(exc)
    else:
        raise AssertionError("expected conflicting task sources to fail")


def test_json_route_does_not_prompt_and_keeps_prompt_out_of_output(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("abr.codex_account_snapshot", lambda: {"available": False, "used_percent": None})
    monkeypatch.setattr("abr.input", lambda _: (_ for _ in ()).throw(AssertionError("must not prompt")), raising=False)
    monkeypatch.setattr("sys.stdin", io.StringIO("Review the routing policy\n"))
    args = build_parser().parse_args([
        "--state-dir", str(tmp_path), "route", "--stdin", "--json",
    ])
    assert command_route(args) == 0
    captured = capsys.readouterr()
    assert "Review the routing policy" not in captured.out
    assert '"task_class"' in captured.out
    assert captured.err == ""


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


def test_route_falls_back_to_cursor_when_codex_allowance_is_unavailable():
    empty = {"runs": 0, "acceptance_rate": None}
    recommendation, confidence, notes = decide_route(0.4, None, empty, empty)
    assert (recommendation, confidence) == ("CURSOR_API", "MEDIUM")
    assert "Codex plan allowance is unavailable" in notes[0]


def test_route_requires_manual_review_when_no_fallback_is_configured():
    empty = {"runs": 0, "acceptance_rate": None}
    recommendation, confidence, notes = decide_route(None, None, empty, empty)
    assert (recommendation, confidence) == ("MANUAL_REVIEW", "LOW")
    assert "Set Cursor API rates" in notes[0]


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


def test_finish_rejects_unknown_preflight_without_probe(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("abr.codex_account_snapshot", lambda: (_ for _ in ()).throw(AssertionError("must not probe")))

    assert command_finish(finish_args(tmp_path, "missing")) == 2
    assert "Unknown preflight ID: missing" in capsys.readouterr().err


def test_finish_rejects_codex_probe_failure_without_recording(tmp_path, monkeypatch, capsys):
    append_run(tmp_path / "preflights.jsonl", {
        "preflight_id": "preflight-1", "task_class": "small_edit",
        "codex_before": {"used_percent": 10},
    })
    monkeypatch.setattr("abr.codex_account_snapshot", lambda: (_ for _ in ()).throw(OSError("codex unavailable")))

    assert command_finish(finish_args(tmp_path)) == 2
    assert "Could not read post-run Codex usage" in capsys.readouterr().err
    assert not (tmp_path / "runs.jsonl").exists()


def test_finish_rejects_double_finish_without_second_probe(tmp_path, monkeypatch, capsys):
    append_run(tmp_path / "preflights.jsonl", {
        "preflight_id": "preflight-1", "task_class": "small_edit",
        "codex_before": {"used_percent": 10},
    })
    append_run(tmp_path / "runs.jsonl", {"preflight_id": "preflight-1"})
    monkeypatch.setattr("abr.codex_account_snapshot", lambda: (_ for _ in ()).throw(AssertionError("must not probe")))

    assert command_finish(finish_args(tmp_path)) == 2
    assert "Preflight is already finished: preflight-1" in capsys.readouterr().err
