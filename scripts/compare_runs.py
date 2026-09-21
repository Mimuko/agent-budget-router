#!/usr/bin/env python3
"""Compare equivalent Cursor API and Codex task measurements.

This script deliberately does not call billing APIs.  A person exports or
transcribes observed usage, then this script makes the calculation and routing
decision reproducible without storing credentials in a skill repository.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"JSON object required: {path}")
    return data


def require_number(data: dict[str, Any], key: str, label: str) -> float:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{label}.{key} must be a non-negative number")
    return float(value)


def optional_number(data: dict[str, Any], key: str, label: str) -> float | None:
    if key not in data or data[key] is None:
        return None
    return require_number(data, key, label)


def validate_common(run: dict[str, Any], label: str) -> None:
    if not isinstance(run.get("task_id"), str) or not run["task_id"].strip():
        raise ValueError(f"{label}.task_id must be a non-empty string")
    if run.get("completion") not in {"completed", "blocked", "failed"}:
        raise ValueError(f"{label}.completion must be completed, blocked, or failed")
    optional_number(run, "elapsed_minutes", label)
    quality = optional_number(run, "quality_score", label)
    if quality is not None and quality > 5:
        raise ValueError(f"{label}.quality_score must be between 0 and 5")


def cursor_cost(run: dict[str, Any]) -> tuple[float | None, str]:
    """Return cost and whether it was observed or calculated from supplied rates."""
    observed = optional_number(run, "api_cost_usd", "cursor")
    if observed is not None:
        return observed, "observed_api_cost"

    usage = run.get("usage")
    rates = run.get("rates_usd_per_mtok")
    if not isinstance(usage, dict) or not isinstance(rates, dict):
        return None, "missing_api_cost_or_rates"
    input_tokens = require_number(usage, "input_tokens", "cursor.usage")
    cached = require_number(usage, "cached_input_tokens", "cursor.usage")
    output = require_number(usage, "output_tokens", "cursor.usage")
    if cached > input_tokens:
        raise ValueError("cursor.usage.cached_input_tokens cannot exceed input_tokens")
    input_rate = require_number(rates, "input", "cursor.rates_usd_per_mtok")
    cached_rate = require_number(rates, "cached_input", "cursor.rates_usd_per_mtok")
    output_rate = require_number(rates, "output", "cursor.rates_usd_per_mtok")
    cost = ((input_tokens - cached) * input_rate + cached * cached_rate + output * output_rate) / 1_000_000
    return cost, "calculated_from_supplied_rates"


def build_recommendation(cursor: dict[str, Any], codex: dict[str, Any], cursor_usd: float | None) -> tuple[str, list[str]]:
    notes: list[str] = []
    if cursor["task_id"] != codex["task_id"]:
        return "NO_RECOMMENDATION", ["task_id differs; compare only equivalent tasks"]
    if cursor["completion"] != "completed" or codex["completion"] != "completed":
        return "NO_RECOMMENDATION", ["both runs must complete before cost routing is decided"]
    c_quality = optional_number(cursor, "quality_score", "cursor")
    d_quality = optional_number(codex, "quality_score", "codex")
    if c_quality is not None and d_quality is not None and abs(c_quality - d_quality) > 0.5:
        return "NO_RECOMMENDATION", ["quality differs by more than 0.5; lower cost is not comparable"]

    mode = codex.get("billing_mode")
    if mode == "included_plan":
        notes.append("Codex used included plan allowance; fixed plan cost is not allocated per task")
        notes.append("Cost recommendation: CODEX (direct marginal cost); confidence: MEDIUM")
        return "CODEX", notes
    if mode != "additional_credit":
        return "NO_RECOMMENDATION", ["codex.billing_mode must be included_plan or additional_credit"]
    codex_usd = optional_number(codex, "additional_credit_usd", "codex")
    if cursor_usd is None or codex_usd is None:
        return "NO_RECOMMENDATION", ["record Cursor API cost and Codex additional-credit USD"]
    if abs(cursor_usd - codex_usd) < 0.005:
        return "EITHER", ["equivalent quality and marginal cost are effectively equal"]
    if cursor_usd < codex_usd:
        return "CURSOR_API", ["equivalent quality; Cursor API has lower observed marginal USD cost"]
    return "CODEX", ["equivalent quality; Codex has lower observed additional-credit USD cost"]


def compare(cursor: dict[str, Any], codex: dict[str, Any], usd_jpy: float | None = None) -> dict[str, Any]:
    validate_common(cursor, "cursor")
    validate_common(codex, "codex")
    if cursor.get("execution") != "cursor_openai_api":
        raise ValueError("cursor.execution must be cursor_openai_api")
    if codex.get("execution") != "codex":
        raise ValueError("codex.execution must be codex")
    if codex.get("billing_mode") not in {"included_plan", "additional_credit"}:
        raise ValueError("codex.billing_mode must be included_plan or additional_credit")

    cursor_usd, cursor_basis = cursor_cost(cursor)
    codex_usd = optional_number(codex, "additional_credit_usd", "codex")
    recommendation, notes = build_recommendation(cursor, codex, cursor_usd)
    result: dict[str, Any] = {
        "task_id": cursor["task_id"],
        "cursor_api": {
            "marginal_cost_usd": cursor_usd,
            "cost_basis": cursor_basis,
            "elapsed_minutes": optional_number(cursor, "elapsed_minutes", "cursor"),
            "quality_score": optional_number(cursor, "quality_score", "cursor"),
        },
        "codex": {
            "billing_mode": codex["billing_mode"],
            "additional_credit_usd": codex_usd,
            "credit_units": optional_number(codex, "credit_units", "codex"),
            "elapsed_minutes": optional_number(codex, "elapsed_minutes", "codex"),
            "quality_score": optional_number(codex, "quality_score", "codex"),
        },
        "recommendation": recommendation,
        "notes": notes,
    }
    if usd_jpy is not None:
        if usd_jpy <= 0:
            raise ValueError("usd_jpy must be positive")
        result["usd_jpy"] = usd_jpy
        result["cursor_api"]["marginal_cost_jpy"] = None if cursor_usd is None else round(cursor_usd * usd_jpy, 2)
        result["codex"]["additional_credit_jpy"] = None if codex_usd is None else round(codex_usd * usd_jpy, 2)
    return result


def render(result: dict[str, Any]) -> str:
    cursor = result["cursor_api"]
    codex = result["codex"]
    lines = [
        "## Agent Cost Comparison",
        "",
        f"Task: {result['task_id']}",
        f"Recommendation: {result['recommendation']}",
        "",
        "| Route | Cost basis | USD | Time | Quality |",
        "| --- | --- | ---: | ---: | ---: |",
        f"| Cursor → OpenAI API | {cursor['cost_basis']} | {fmt(cursor['marginal_cost_usd'])} | {fmt(cursor['elapsed_minutes'])} min | {fmt(cursor['quality_score'])}/5 |",
        f"| Codex | {codex['billing_mode']} | {fmt(codex['additional_credit_usd'])} | {fmt(codex['elapsed_minutes'])} min | {fmt(codex['quality_score'])}/5 |",
        "",
        "Notes:",
    ]
    lines.extend(f"- {note}" for note in result["notes"])
    return "\n".join(lines)


def fmt(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare Cursor API and Codex observed task costs")
    parser.add_argument("--cursor", required=True, type=Path, help="Cursor → OpenAI API measurement JSON")
    parser.add_argument("--codex", required=True, type=Path, help="Codex measurement JSON")
    parser.add_argument("--usd-jpy", type=float, help="Optional observed USD/JPY rate used for display only")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    args = parser.parse_args(argv)
    try:
        result = compare(load_json(args.cursor), load_json(args.codex), args.usd_jpy)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
