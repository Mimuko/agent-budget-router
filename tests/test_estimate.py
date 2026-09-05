"""Tests for agent-budget-router estimate.py"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from estimate import (  # noqa: E402
    detect_exploration_pattern,
    estimate,
    score_complexity,
    score_to_complexity,
)


def test_single_file_low_complexity():
    task = "Fix typo in README.md — one file only"
    score = score_complexity(task)
    assert score <= 1
    complexity = score_to_complexity(score)
    assert complexity in ("LOW", "MEDIUM")
    pattern = detect_exploration_pattern(task, complexity)
    assert pattern == "single-file edit"


def test_architecture_high_complexity():
    task = "初回調査: AgentPlugin 横断再設計と routing-policy 全体の要件定義"
    score = score_complexity(task)
    assert score >= 3
    complexity = score_to_complexity(score)
    assert complexity in ("HIGH", "CRITICAL")
    pattern = detect_exploration_pattern(task, complexity)
    assert pattern in ("cross-cutting change", "architecture / unknown repo")


def test_estimate_returns_required_keys():
    result = estimate("Fix CSS in header.css")
    required = {
        "verdict",
        "complexity",
        "exploration_pattern",
        "confidence",
        "estimated_context",
        "estimated_generation",
        "exploration_factor",
        "recommended_phases",
    }
    assert required.issubset(result.keys())
    assert result["estimated_context"]["min"] <= result["estimated_context"]["max"]


def test_large_task_split_recommended():
    result = estimate(
        "Implement full AgentPlugin architecture redesign across all plugins",
        skill_count=10,
    )
    assert result["verdict"] in ("SPLIT_RECOMMENDED", "DEFER")
    assert result["complexity"] in ("HIGH", "CRITICAL")
    assert len(result["recommended_phases"]) >= 2


def test_budget_tight_defers_critical():
    result = estimate(
        "大規模 Plugin 実装と横断 refactor",
        budget_tight=True,
    )
    if result["complexity"] in ("HIGH", "CRITICAL"):
        assert result["verdict"] == "DEFER"


def test_cli_json_output():
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "estimate.py"),
            "Fix typo in one file",
            "--json",
        ],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["verdict"] == "GO"
    assert data["complexity"] == "LOW"
