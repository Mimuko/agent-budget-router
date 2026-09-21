"""Tests for observed Cursor API / Codex cost comparisons."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from compare_runs import compare  # noqa: E402


def cursor_run(**overrides):
    run = {
        "task_id": "same-task",
        "execution": "cursor_openai_api",
        "completion": "completed",
        "elapsed_minutes": 10,
        "quality_score": 4.5,
        "api_cost_usd": 0.42,
    }
    run.update(overrides)
    return run


def codex_run(**overrides):
    run = {
        "task_id": "same-task",
        "execution": "codex",
        "completion": "completed",
        "billing_mode": "additional_credit",
        "additional_credit_usd": 0.31,
        "elapsed_minutes": 8,
        "quality_score": 4.5,
    }
    run.update(overrides)
    return run


def test_routes_to_lower_additional_cost_for_equivalent_quality():
    result = compare(cursor_run(), codex_run())
    assert result["recommendation"] == "CODEX"


def test_included_plan_is_not_ranked_as_zero_cost():
    result = compare(cursor_run(), codex_run(billing_mode="included_plan", additional_credit_usd=None))
    assert result["recommendation"] == "MANUAL_REVIEW"


def test_calculates_cursor_cost_from_usage_and_supplied_rates():
    cursor = cursor_run(
        api_cost_usd=None,
        usage={"input_tokens": 1_000_000, "cached_input_tokens": 200_000, "output_tokens": 100_000},
        rates_usd_per_mtok={"input": 2, "cached_input": 0.2, "output": 10},
    )
    result = compare(cursor, codex_run(additional_credit_usd=2.0))
    assert result["cursor_api"]["cost_basis"] == "calculated_from_supplied_rates"
    assert result["cursor_api"]["marginal_cost_usd"] == 2.64
    assert result["recommendation"] == "CODEX"


def test_quality_difference_requires_manual_decision():
    result = compare(cursor_run(quality_score=3.5), codex_run(quality_score=4.5))
    assert result["recommendation"] == "NO_RECOMMENDATION"


def test_cli_outputs_json_for_examples():
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "compare_runs.py"),
            "--cursor",
            str(ROOT / "examples" / "measurements" / "cursor-api.json"),
            "--codex",
            str(ROOT / "examples" / "measurements" / "codex-additional-credit.json"),
            "--json",
        ],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["recommendation"] == "CODEX"
