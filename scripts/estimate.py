#!/usr/bin/env python3
"""Agent Budget Router — estimate expected agent context before delegation."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

EXPLORATION_PATTERNS: dict[str, tuple[float, float]] = {
    "single-file edit": (1.1, 1.3),
    "known feature area": (1.3, 1.6),
    "cross-cutting change": (1.5, 2.0),
    "architecture / unknown repo": (1.8, 3.0),
}

RELEVANT_FILES_BY_PATTERN: dict[str, tuple[int, int]] = {
    "single-file edit": (2_000, 8_000),
    "known feature area": (8_000, 40_000),
    "cross-cutting change": (25_000, 80_000),
    "architecture / unknown repo": (50_000, 200_000),
}

GENERATION_BY_COMPLEXITY: dict[str, tuple[int, int]] = {
    "LOW": (2_000, 8_000),
    "MEDIUM": (8_000, 25_000),
    "HIGH": (20_000, 60_000),
    "CRITICAL": (40_000, 120_000),
}

ARCHITECTURE_SIGNALS = [
    r"\barchitecture\b",
    r"\barchitect\b",
    r"初回",
    r"全体",
    r"横断",
    r"要件定義",
    r"plugin",
    r"agentplugin",
    r"再設計",
    r"redesign",
    r"unknown repo",
    r"初めて",
    r"大規模",
    r"large.?scale",
    r"full.?repo",
]

CROSS_CUTTING_SIGNALS = [
    r"複数",
    r"multiple",
    r"across",
    r"policy",
    r"共通",
    r"\bplugins\b",
    r"\brules\b",
    r"\bskills\b",
    r"横断",
    r"refactor",
    r"リファクタ",
]

SINGLE_FILE_SIGNALS = [
    r"1\s*ファイル",
    r"one file",
    r"single file",
    r"typo",
    r"css\s*1",
    r"1\s*枚",
    r"\.css\b",
    r"\.md\b.*修正",
    r"lint fix",
    r"typo fix",
]

KNOWN_AREA_SIGNALS = [
    r"機能追加",
    r"add feature",
    r"既存",
    r"existing",
    r"module",
    r"モジュール",
    r"component",
    r"fix bug",
    r"バグ修正",
]

COMPLEXITY_BOOST = [
    (ARCHITECTURE_SIGNALS, 2),
    (CROSS_CUTTING_SIGNALS, 1),
]
COMPLEXITY_REDUCE = [
    (SINGLE_FILE_SIGNALS, 2),
]


def load_yaml_simple(path: Path) -> dict[str, Any]:
    """Minimal YAML loader for flat catalog files (no external deps)."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    return _parse_yaml(text)


def _parse_yaml(text: str) -> dict[str, Any]:
    """Parse a restricted subset of YAML used by catalog files."""
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ImportError:
        return _parse_yaml_fallback(text)


def _parse_yaml_fallback(text: str) -> dict[str, Any]:
    """Very small fallback when PyYAML is unavailable."""
    result: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, result)]
    key_re = re.compile(r"^(\s*)(\w[\w.-]*):\s*(.*)$")

    for line in text.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        m = key_re.match(line)
        if not m:
            continue
        indent = len(m.group(1))
        key = m.group(2)
        value = m.group(3).strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if value == "":
            parent[key] = {}
            stack.append((indent, parent[key]))
        elif value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            parent[key] = (
                [v.strip().strip('"').strip("'") for v in inner.split(",") if v.strip()]
                if inner
                else []
            )
        elif value in ("null", "~"):
            parent[key] = None
        elif value.startswith('"') and value.endswith('"'):
            parent[key] = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            parent[key] = value[1:-1]
        else:
            try:
                parent[key] = int(value)
            except ValueError:
                try:
                    parent[key] = float(value)
                except ValueError:
                    parent[key] = value
    return result


def _matches_any(text: str, patterns: list[str]) -> bool:
    lower = text.lower()
    return any(re.search(p, lower, re.IGNORECASE) for p in patterns)


def count_file_hints(text: str) -> int:
    paths = re.findall(r"[\w./\\-]+\.(?:py|ts|tsx|js|jsx|css|md|yaml|yml|json|html|go|rs)", text)
    return len(set(paths))


def score_complexity(task: str) -> int:
    score = 0
    for patterns, pts in COMPLEXITY_BOOST:
        if _matches_any(task, patterns):
            score += pts
    for patterns, pts in COMPLEXITY_REDUCE:
        if _matches_any(task, patterns):
            score -= pts
    file_hints = count_file_hints(task)
    if file_hints >= 10:
        score += 2
    elif file_hints >= 5:
        score += 1
    if re.search(r"複数.*(システム|repo|repository)", task, re.IGNORECASE):
        score += 2
    if re.search(r"明確|スコープ.*限定|only\b|clear acceptance", task, re.IGNORECASE):
        score -= 1
    if _matches_any(task, KNOWN_AREA_SIGNALS) and not _matches_any(task, SINGLE_FILE_SIGNALS):
        score += 2
    return score


def score_to_complexity(score: int) -> str:
    if score <= 0:
        return "LOW"
    if score <= 2:
        return "MEDIUM"
    if score <= 4:
        return "HIGH"
    return "CRITICAL"


def detect_exploration_pattern(task: str, complexity: str) -> str:
    if _matches_any(task, SINGLE_FILE_SIGNALS) and complexity == "LOW":
        return "single-file edit"
    if _matches_any(task, ARCHITECTURE_SIGNALS) or complexity == "CRITICAL":
        return "architecture / unknown repo"
    if _matches_any(task, KNOWN_AREA_SIGNALS) and complexity in ("LOW", "MEDIUM"):
        return "known feature area"
    if _matches_any(task, CROSS_CUTTING_SIGNALS) or complexity == "HIGH":
        return "cross-cutting change"
    if _matches_any(task, KNOWN_AREA_SIGNALS) or complexity == "MEDIUM":
        return "known feature area"
    mapping = {
        "LOW": "single-file edit",
        "MEDIUM": "known feature area",
        "HIGH": "cross-cutting change",
        "CRITICAL": "architecture / unknown repo",
    }
    return mapping[complexity]


def resolve_lane_model(
    lane_name: str,
    lane_cfg: dict[str, Any],
    models: dict[str, Any],
) -> dict[str, Any]:
    model_id = lane_cfg.get("model")
    effort = lane_cfg.get("effort")
    speed = lane_cfg.get("speed")
    result: dict[str, Any] = {
        "lane": lane_name,
        "model": model_id,
        "effort": effort,
        "speed": speed,
        "display_name": None,
        "resolved": None,
        "error": None,
    }
    if model_id is None:
        result["resolved"] = "parent model (auto-lane)"
        result["display_name"] = "Parent model"
        return result
    model_entry = models.get(model_id)
    if not model_entry:
        result["error"] = f"Unregistered model - update catalog: {model_id}"
        result["resolved"] = model_id
        return result
    result["display_name"] = model_entry.get("display_name", model_id)
    parts = [model_id]
    params = []
    if effort:
        params.append(f"effort={effort}")
    if speed:
        params.append(f"speed={speed}")
    if params:
        result["resolved"] = f"{model_id} ({', '.join(params)})"
    else:
        result["resolved"] = model_id
    return result


def build_phases(
    complexity: str,
    lanes: dict[str, Any],
    models: dict[str, Any],
) -> list[dict[str, Any]]:
    phases: list[dict[str, Any]] = []
    if complexity in ("LOW",):
        lane = resolve_lane_model("auto-lane", lanes.get("auto-lane", {}), models)
        phases.append({"phase": "Execution", **lane})
        return phases
    if complexity == "MEDIUM":
        lane = resolve_lane_model("implementer", lanes.get("implementer", {}), models)
        phases.append({"phase": "Execution", **lane})
        return phases
    plan = resolve_lane_model("analyst-planner", lanes.get("analyst-planner", {}), models)
    impl = resolve_lane_model("implementer", lanes.get("implementer", {}), models)
    review = resolve_lane_model("cross-reviewer", lanes.get("cross-reviewer", {}), models)
    phases.extend(
        [
            {"phase": "Planning", **plan},
            {"phase": "Execution", **impl},
            {"phase": "Review", **review},
        ]
    )
    return phases


def compute_confidence(
    task: str,
    scan: dict[str, Any] | None,
    path_hints: list[str] | None,
) -> str:
    has_paths = bool(path_hints) or count_file_hints(task) > 0
    has_scan = bool(scan and scan.get("candidate_files"))
    high_rel = bool(scan and scan.get("high_relevance_count", 0) >= 2)
    if has_scan and has_paths and high_rel:
        return "HIGH"
    if has_scan and high_rel:
        return "HIGH"
    if has_scan and has_paths:
        return "HIGH"
    if has_scan or has_paths:
        return "MEDIUM"
    return "LOW"


def agent_overhead_label(pattern: str) -> str:
    if pattern in ("cross-cutting change", "architecture / unknown repo"):
        return "HIGH"
    if pattern == "known feature area":
        return "MEDIUM"
    return "LOW"


def determine_verdict(
    complexity: str,
    context_max: int,
    budget_tight: bool,
    confidence: str,
) -> str:
    if budget_tight and complexity in ("HIGH", "CRITICAL"):
        return "DEFER"
    if complexity == "CRITICAL" and confidence == "LOW":
        return "DEFER"
    if complexity in ("HIGH", "CRITICAL"):
        return "SPLIT_RECOMMENDED"
    if complexity == "MEDIUM" and context_max >= 150_000:
        return "SPLIT_RECOMMENDED"
    return "GO"


def build_budget_risks(
    complexity: str,
    pattern: str,
    skill_count: int,
    phases: list[dict[str, Any]],
) -> list[str]:
    risks: list[str] = []
    if complexity in ("HIGH", "CRITICAL"):
        risks.append("High-cost route if run entirely on frontier model")
        risks.append("Split planning (high effort) from implementation (Composer)")
    if pattern == "architecture / unknown repo":
        risks.append("Unknown repo / architecture tasks tend to re-read and explore heavily")
    if skill_count >= 3:
        risks.append("Skill/Plugin overhead is significant - scope active rules before agent run")
    frontier = [p for p in phases if p.get("effort") in ("high", "xhigh")]
    if len(phases) >= 3 and frontier:
        risks.append("Multi-phase split recommended - do not run all phases on one frontier model")
    if not risks:
        risks.append("Low budget risk for single-lane execution")
    return risks


def build_next_actions(verdict: str, complexity: str, phases: list[dict[str, Any]]) -> list[str]:
    if verdict == "GO":
        lane = phases[0].get("lane", "auto-lane") if phases else "auto-lane"
        return [
            f"Proceed with single lane `{lane}`",
            "Fix scope in one sentence before starting the agent",
            "Record usage after completion (for future calibration)",
        ]
    if verdict == "SPLIT_RECOMMENDED":
        return [
            "Split scope into N sub-tasks",
            "Run analyst-planner for planning only first",
            "Delegate implementation to implementer; use cross-reviewer for important changes",
        ]
    return [
        "Clarify task description and target paths, then re-estimate",
        "Human decides scope and budget ceiling",
        "Run analyst-planner (readonly) for initial investigation only",
    ]


def estimate(
    task: str,
    *,
    path_hints: list[str] | None = None,
    skill_count: int = 0,
    budget_tight: bool = False,
    scan: dict[str, Any] | None = None,
    catalog_dir: Path | None = None,
) -> dict[str, Any]:
    catalog_dir = catalog_dir or ROOT / "catalog"
    models_data = load_yaml_simple(catalog_dir / "models.default.yaml")
    lanes_data = load_yaml_simple(catalog_dir / "lanes.default.yaml")
    models = models_data.get("models", {})
    lanes = lanes_data.get("lanes", {})

    complexity_score = score_complexity(task)
    complexity = score_to_complexity(complexity_score)
    pattern = detect_exploration_pattern(task, complexity)
    exp_min, exp_max = EXPLORATION_PATTERNS[pattern]

    task_baseline = (3_000, 12_000)
    rel_min, rel_max = RELEVANT_FILES_BY_PATTERN[pattern]

    if scan and scan.get("estimated_tokens"):
        tok = scan["estimated_tokens"]
        rel_min = int(tok.get("min", rel_min))
        rel_max = int(tok.get("max", rel_max))

    skill_overhead = (2_000 * skill_count, 15_000 * skill_count) if skill_count else (0, 0)

    base_min = task_baseline[0] + rel_min + skill_overhead[0]
    base_max = task_baseline[1] + rel_max + skill_overhead[1]

    ctx_min = int(base_min * exp_min)
    ctx_max = int(base_max * exp_max)

    gen_min, gen_max = GENERATION_BY_COMPLEXITY[complexity]
    if complexity in ("HIGH", "CRITICAL"):
        gen_min = int(gen_min * 1.5)
        gen_max = int(gen_max * 2.0)

    confidence = compute_confidence(task, scan, path_hints)
    verdict = determine_verdict(complexity, ctx_max, budget_tight, confidence)
    phases = build_phases(complexity, lanes, models)
    overhead = agent_overhead_label(pattern)
    risks = build_budget_risks(complexity, pattern, skill_count, phases)
    actions = build_next_actions(verdict, complexity, phases)

    return {
        "verdict": verdict,
        "complexity": complexity,
        "exploration_pattern": pattern,
        "confidence": confidence,
        "estimated_context": {"min": ctx_min, "max": ctx_max},
        "estimated_generation": {"min": gen_min, "max": gen_max},
        "exploration_factor": {"min": exp_min, "max": exp_max, "label": pattern},
        "agent_overhead": overhead,
        "recommended_phases": phases,
        "budget_risk": risks,
        "next_actions": actions,
        "signals": {
            "complexity_score": complexity_score,
            "task_baseline": {"min": task_baseline[0], "max": task_baseline[1]},
            "relevant_files": {"min": rel_min, "max": rel_max},
            "skill_overhead": {"min": skill_overhead[0], "max": skill_overhead[1]},
        },
    }


def extract_task_text(raw: str) -> str:
    """Use task body only when reading example markdown files."""
    if "## Expected output" in raw or "## Run" in raw:
        # Example file: take body between title block and ## Expected / ## Run
        lines = raw.splitlines()
        body: list[str] = []
        started = False
        for line in lines:
            if line.startswith("## Expected") or line.startswith("## Run"):
                break
            if line.startswith("# "):
                started = True
                continue
            if started:
                body.append(line)
        task = "\n".join(body).strip()
        if task:
            return task
    return raw.strip()


def format_tokens(n: int) -> str:
    if n >= 1000:
        val = n / 1000
        return f"{val:.0f}k" if val == int(val) else f"{val:.1f}k"
    return str(n)


def _dash() -> str:
    """ASCII hyphen for Windows console compatibility."""
    return "-"


def render_report(result: dict[str, Any]) -> str:
    ctx = result["estimated_context"]
    gen = result["estimated_generation"]
    exp = result["exploration_factor"]
    d = _dash()
    lines = [
        "## Agent Budget Report",
        "",
        f"Verdict: {result['verdict']}",
        f"Task complexity: {result['complexity']}",
        f"Exploration pattern: {result['exploration_pattern']}",
        f"Confidence: {result['confidence']}",
        "",
        f"Estimated context:     {format_tokens(ctx['min'])} {d} {format_tokens(ctx['max'])} tokens",
        "  (expected agent context - not full repository size)",
        f"Estimated generation:   {format_tokens(gen['min'])} {d}  {format_tokens(gen['max'])} tokens",
        f"Exploration factor:    x{exp['min']}{d}{exp['max']} ({exp['label']})",
        f"Agent overhead:        {result['agent_overhead']}",
        "",
        "Recommended phases:",
    ]
    for phase in result["recommended_phases"]:
        name = phase.get("display_name") or phase.get("model") or "parent model"
        resolved = phase.get("resolved", "")
        err = phase.get("error")
        suffix = f" - {err}" if err else ""
        lines.append(f"  {phase['phase']:<10} -> {phase['lane']:<18} ({name}, {resolved}){suffix}")
    lines.extend(
        [
            "",
            "Budget risk:",
        ]
    )
    for risk in result["budget_risk"]:
        lines.append(f"  {risk}")
    lines.extend(
        [
            "",
            "Why this exists:",
            "  I gave a large AgentPlugin implementation task to a high-end agent model",
            "  and burned through the entire usage allowance before I could tell",
            "  whether the model was actually better.",
            "",
            "Next actions:",
        ]
    )
    for i, action in enumerate(result["next_actions"], 1):
        lines.append(f"  {i}. {action}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Estimate agent budget before delegation")
    parser.add_argument("task", nargs="?", help="Task description")
    parser.add_argument("--task-file", type=Path, help="Read task from file")
    parser.add_argument("--path-hint", action="append", dest="path_hints", default=[])
    parser.add_argument("--skill-count", type=int, default=0, help="Active skills/rules count")
    parser.add_argument("--budget-tight", action="store_true", help="User flagged tight budget")
    parser.add_argument("--scan-json", type=Path, help="scan_workspace.py output JSON")
    parser.add_argument("--catalog-dir", type=Path, default=ROOT / "catalog")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    args = parser.parse_args(argv)

    if args.task_file:
        task = extract_task_text(args.task_file.read_text(encoding="utf-8"))
    elif args.task:
        task = args.task
    else:
        task = sys.stdin.read().strip()

    if not task:
        parser.error("Task description required (arg, --task-file, or stdin)")

    scan = None
    if args.scan_json and args.scan_json.exists():
        scan = json.loads(args.scan_json.read_text(encoding="utf-8"))

    result = estimate(
        task,
        path_hints=args.path_hints or None,
        skill_count=args.skill_count,
        budget_tight=args.budget_tight,
        scan=scan,
        catalog_dir=args.catalog_dir,
    )

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(render_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
