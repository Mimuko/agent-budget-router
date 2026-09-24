"""Skill v1 Core contract tests."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import abr_core  # noqa: E402
from abr import route_preflight  # noqa: E402


def task_estimate(base="DIRECT"):
    return {
        "task_class": "feature_build",
        "estimated_context": {"min": 10, "max": 20},
        "estimated_generation": {"min": 2, "max": 4},
        "base_recommendation": base,
        "base_reason": "feature_build",
    }


def budget(remaining, task):
    return {
        "remaining_ratio": remaining,
        "estimated_task_ratio": task,
        "snapshot_at": "2026-09-24T02:00:00Z",
        "scope": "account",
    }


def test_should_preflight_uses_lightweight_signals_without_estimation(monkeypatch):
    monkeypatch.setattr(abr_core, "estimate_task_size", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not estimate")))
    assert abr_core.should_preflight("READMEの誤字修正して")["decision"] == "SKIP"
    assert abr_core.should_preflight("MY-172を実装して")["decision"] == "PREFLIGHT"
    assert abr_core.should_preflight("複数ファイルの設計を更新")["decision"] == "PREFLIGHT"
    assert abr_core.should_preflight(" ")["decision"] == "INPUT_UNAVAILABLE"


def test_estimate_task_maps_existing_estimate_and_is_deterministic(monkeypatch):
    calls = []

    def legacy(text, **kwargs):
        calls.append((text, kwargs))
        return {
            "verdict": "SPLIT_RECOMMENDED",
            "exploration_pattern": "cross-cutting change",
            "estimated_context": {"min": 42, "max": 184},
            "estimated_generation": {"min": 8, "max": 25},
        }

    monkeypatch.setattr(abr_core, "estimate_task_size", legacy)
    context = {"title": "Feature", "summary": "Across modules", "path_hints": ["src/app.py"]}
    first = abr_core.estimate_task("Implement feature", context)
    second = abr_core.estimate_task("Implement feature", context)
    assert first == second
    assert first == {
        "task_class": "cross_cutting",
        "estimated_context": {"min": 42, "max": 184},
        "estimated_generation": {"min": 8, "max": 25},
        "base_recommendation": "SPLIT",
        "base_reason": "cross_cutting",
    }
    assert calls[0][1]["path_hints"] == ["src/app.py"]


@pytest.mark.parametrize("legacy_verdict,expected", [
    ("GO", "DIRECT"), ("SPLIT_RECOMMENDED", "SPLIT"), ("DEFER", "DEFER"),
])
def test_all_legacy_verdicts_stay_inside_core(monkeypatch, legacy_verdict, expected):
    monkeypatch.setattr(abr_core, "estimate_task_size", lambda *_args, **_kwargs: {
        "verdict": legacy_verdict,
        "exploration_pattern": "known feature area",
        "estimated_context": {"min": 10, "max": 20},
        "estimated_generation": {"min": 2, "max": 4},
    })
    sized = abr_core.estimate_task("Implement feature")
    assert sized["base_recommendation"] == expected
    assert "verdict" not in sized


@pytest.mark.parametrize("remaining,task,expected,reason", [
    (0.5, 0.25, "DIRECT", "feature_build"),
    (0.5, 0.2501, "SPLIT", "budget_limited"),
    (0.4, 0.4, "SPLIT", "budget_limited"),
    (0.4, 0.4001, "DEFER", "budget_exceeded"),
    (0, 0.01, "DEFER", "budget_exhausted"),
])
def test_budget_thresholds(remaining, task, expected, reason):
    result = abr_core.route(task_estimate(), budget(remaining, task))
    assert result["recommended_policy"] == expected
    assert result["recommendation_reason"] == reason
    assert result["base_reason"] == "feature_build"


def test_no_budget_uses_base_and_explains_fallback():
    source = task_estimate()
    result = abr_core.route(source)
    assert result["recommended_policy"] == "DIRECT"
    assert result["recommendation_reason"] == "budget_unavailable"
    assert result["base_reason"] == "feature_build"
    assert source == task_estimate()


@pytest.mark.parametrize("base", ["SPLIT", "DEFER"])
def test_budget_cannot_relax_base_recommendation(base):
    result = abr_core.route(task_estimate(base), budget(0.8, 0.05))
    assert result["recommended_policy"] == base
    assert result["recommendation_reason"] == "feature_build"


@pytest.mark.parametrize("bad", [
    {**task_estimate(), "base_recommendation": "GO"},
    {**task_estimate(), "estimated_context": {"min": 10, "max": 9}},
    {**task_estimate(), "base_reason": ""},
])
def test_invalid_task_estimate_fails_without_reestimating(monkeypatch, bad):
    monkeypatch.setattr(abr_core, "estimate_task_size", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not estimate")))
    with pytest.raises(ValueError):
        abr_core.route(bad)


@pytest.mark.parametrize("bad", [
    budget(1.01, 0.1), budget(-0.1, 0.1), budget(0.5, -0.1),
    budget(True, 0.1), budget(0.5, float("nan")),
    {**budget(0.5, 0.1), "scope": ""},
])
def test_invalid_budget_context_fails(bad):
    with pytest.raises(ValueError):
        abr_core.route(task_estimate(), bad)


def test_estimated_task_ratio_above_one_is_valid():
    assert abr_core.route(task_estimate(), budget(0.5, 1.2))["recommended_policy"] == "DEFER"


def test_legacy_route_preflight_wrapper_keeps_confirmation_shape():
    result = route_preflight("複数モジュールの設計を更新")
    assert result["execution_policy"] == "CONFIRM_FIRST"
    assert result["gate"] == {"level": "CONFIRM", "action": "ASK_USER"}
    assert result["recommended_policy"] in ("DIRECT", "SPLIT", "DEFER")
    assert "verdict" not in result
