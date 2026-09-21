#!/usr/bin/env python3
"""Daily CLI for history-backed Agent Budget Router decisions.

``compare_runs.py`` remains useful for a controlled experiment.  This command
is the normal entry point: it estimates a route before work and stores compact,
non-sensitive run facts after work.  It never writes prompts, source code, API
keys, or Codex session transcripts to its state directory.
"""

from __future__ import annotations

import argparse
import json
import queue
import statistics
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from estimate import estimate


DEFAULT_STATE_DIR = Path.home() / ".agent-budget-router"


def state_paths(state_dir: Path) -> tuple[Path, Path]:
    return state_dir / "config.json", state_dir / "runs.jsonl"


def read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    return value if isinstance(value, dict) else default


def read_runs(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    runs: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            run = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at {path}:{number}: {exc}") from exc
        if isinstance(run, dict):
            runs.append(run)
    return runs


def append_run(path: Path, run: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(run, ensure_ascii=False, separators=(",", ":")) + "\n")


def append_snapshot(state_dir: Path, snapshot: dict[str, Any]) -> Path:
    path = state_dir / "usage-snapshots.jsonl"
    append_run(path, {"timestamp": datetime.now(UTC).isoformat(), **snapshot})
    return path


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


def median(values: list[float]) -> float | None:
    return round(float(statistics.median(values)), 3) if values else None


def route_stats(runs: list[dict[str, Any]], kind: str, route: str) -> dict[str, Any]:
    relevant = [r for r in runs if r.get("task_class") == kind and r.get("route") == route]
    completed = [r for r in relevant if r.get("completion") == "completed"]
    accepted = [r for r in completed if r.get("acceptance") == "satisfied"]
    return {
        "runs": len(relevant),
        "completed": len(completed),
        "acceptance_rate": None if not completed else round(len(accepted) / len(completed), 2),
        "median_cost_usd": median([float(r["cost_usd"]) for r in completed if isinstance(r.get("cost_usd"), (int, float))]),
        "median_elapsed_minutes": median([float(r["elapsed_minutes"]) for r in completed if isinstance(r.get("elapsed_minutes"), (int, float))]),
        "median_credits": median([float(r["credit_units"]) for r in completed if isinstance(r.get("credit_units"), (int, float))]),
    }


def codex_account_snapshot(timeout_seconds: float = 6.0) -> dict[str, Any]:
    """Read current Codex plan/rate-limit state through its supported app server."""
    process = subprocess.Popen(
        ["codex", "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", bufsize=1,
    )
    assert process.stdin and process.stdout
    messages: queue.Queue[dict[str, Any]] = queue.Queue()

    def receive() -> None:
        for line in process.stdout:
            try:
                messages.put(json.loads(line))
            except json.JSONDecodeError:
                continue

    reader = threading.Thread(target=receive, daemon=True)
    reader.start()
    requests = [
        {"method": "initialize", "id": 0, "params": {"clientInfo": {"name": "agent_budget_router", "title": "Agent Budget Router", "version": "1.0"}}},
        {"method": "initialized", "params": {}},
        {"method": "account/read", "id": 1, "params": {"refreshToken": False}},
        {"method": "account/rateLimits/read", "id": 2, "params": {}},
        {"method": "account/usage/read", "id": 3, "params": {}},
    ]
    for request in requests:
        process.stdin.write(json.dumps(request) + "\n")
    process.stdin.flush()
    responses: dict[int, dict[str, Any]] = {}
    deadline = datetime.now().timestamp() + timeout_seconds
    try:
        while datetime.now().timestamp() < deadline and len(responses) < 4:
            try:
                message = messages.get(timeout=0.15)
            except queue.Empty:
                continue
            if isinstance(message.get("id"), int):
                responses[message["id"]] = message
    finally:
        process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()

    account = responses.get(1, {}).get("result", {}).get("account") or {}
    rate_limits = responses.get(2, {}).get("result", {}).get("rateLimits") or {}
    primary = rate_limits.get("primary") or {}
    used = primary.get("usedPercent")
    available = account.get("type") == "chatgpt" and isinstance(used, (int, float)) and used < 100
    return {
        "source": "codex_app_server",
        "available": available,
        "plan_type": account.get("planType"),
        "used_percent": used,
        "usage_summary": responses.get(3, {}).get("result", {}).get("summary"),
    }


def cursor_estimated_cost(result: dict[str, Any], config: dict[str, Any]) -> float | None:
    rates = config.get("cursor_api_rates_usd_per_mtok")
    if not isinstance(rates, dict):
        return None
    try:
        input_rate = float(rates["input"])
        cached_rate = float(rates["cached_input"])
        output_rate = float(rates["output"])
        cache_ratio = float(config.get("cursor_cached_input_ratio", 0))
    except (KeyError, TypeError, ValueError):
        return None
    if not 0 <= cache_ratio <= 1:
        return None
    context = result["estimated_context"]["max"]
    generation = result["estimated_generation"]["max"]
    cached = context * cache_ratio
    return round(((context - cached) * input_rate + cached * cached_rate + generation * output_rate) / 1_000_000, 4)


def decide_route(cursor_cost: float | None, codex: dict[str, Any] | None, cursor: dict[str, Any], codex_history: dict[str, Any]) -> tuple[str, str, list[str]]:
    notes: list[str] = []
    if codex and codex.get("available"):
        notes.append("Codex plan allowance is currently available")
        if codex_history["runs"] >= 3 and codex_history["acceptance_rate"] is not None:
            notes.append(f"Codex historical acceptance rate: {codex_history['acceptance_rate']:.0%}")
            return "CODEX", "HIGH", notes
        notes.append("Need 3 comparable Codex runs for a high-confidence performance trend")
        return "CODEX", "MEDIUM", notes
    if cursor_cost is not None:
        notes.append("Codex plan allowance is unavailable or could not be read")
        return "CURSOR_API", "MEDIUM", notes
    notes.append("Set Cursor API rates and/or connect a logged-in Codex app-server")
    return "MANUAL_REVIEW", "LOW", notes


def command_route(args: argparse.Namespace) -> int:
    state_dir = args.state_dir.expanduser()
    config_path, runs_path = state_paths(state_dir)
    config, runs = read_json(config_path, {}), read_runs(runs_path)
    result = estimate(args.task, path_hints=args.path_hints or None, skill_count=args.skill_count)
    kind = task_class(args.task, result["exploration_pattern"])
    codex = None
    if not args.no_codex_probe:
        try:
            codex = codex_account_snapshot()
        except (OSError, subprocess.SubprocessError, ValueError):
            codex = {"available": False, "source": "unavailable"}
    cursor_history = route_stats(runs, kind, "cursor_api")
    codex_history = route_stats(runs, kind, "codex")
    cursor_cost = cursor_estimated_cost(result, config)
    recommendation, confidence, notes = decide_route(cursor_cost, codex, cursor_history, codex_history)
    output = {
        "task_class": kind,
        "estimated_context": result["estimated_context"],
        "estimated_generation": result["estimated_generation"],
        "cursor_api": {"estimated_cost_usd": cursor_cost, "historical": cursor_history},
        "codex": {"allowance": codex, "historical": codex_history},
        "suggested_execution": recommendation,
        "confidence": confidence,
        "reasons": notes,
    }
    if args.json:
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(f"Estimated task class: {kind}")
        print(f"Estimated context: {result['estimated_context']['max'] // 1000}k tokens")
        print(f"Likely output: {result['estimated_generation']['max'] // 1000}k tokens\n")
        print(f"Cursor API estimated cost: {format_usd(cursor_cost)}")
        allowance = "available" if codex and codex.get("available") else "unavailable / not readable"
        print(f"Codex plan allowance: {allowance}")
        print(f"Codex historical median: {format_number(codex_history['median_elapsed_minutes'], 'min')}, {codex_history['runs']} runs\n")
        print(f"Suggested execution: {recommendation}")
        print(f"Confidence: {confidence}")
        for note in notes:
            print(f"Reason: {note}")
    return 0


def command_record(args: argparse.Namespace) -> int:
    _, runs_path = state_paths(args.state_dir.expanduser())
    run = {
        "timestamp": datetime.now(UTC).isoformat(), "task_class": args.task_class, "route": args.route,
        "completion": args.completion, "acceptance": args.acceptance, "elapsed_minutes": args.elapsed_minutes,
        "cost_usd": args.cost_usd, "credit_units": args.credit_units,
        "checks": {"tests": args.tests, "lint": args.lint, "build": args.build}, "human_revisions": args.human_revisions,
    }
    append_run(runs_path, {key: value for key, value in run.items() if value is not None})
    print(f"Recorded {args.route} run in {runs_path}")
    return 0


def command_configure(args: argparse.Namespace) -> int:
    config_path, _ = state_paths(args.state_dir.expanduser())
    config = read_json(config_path, {})
    config["cursor_api_rates_usd_per_mtok"] = {
        "input": args.input_rate,
        "cached_input": args.cached_input_rate,
        "output": args.output_rate,
    }
    config["cursor_cached_input_ratio"] = args.cached_input_ratio
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved Cursor API rate settings to {config_path}")
    return 0


def command_capture_codex(args: argparse.Namespace) -> int:
    """Persist a global Codex usage snapshot without exposing account details."""
    try:
        snapshot = codex_account_snapshot()
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"Could not read Codex usage: {exc}", file=sys.stderr)
        return 2
    path = append_snapshot(args.state_dir.expanduser(), snapshot)
    usage = snapshot.get("usage_summary") or {}
    print(f"Captured Codex allowance={snapshot.get('available')} used={snapshot.get('used_percent')}% to {path}")
    if usage.get("lifetimeTokens") is not None:
        print(f"Lifetime tokens reported by Codex: {usage['lifetimeTokens']}")
    return 0


def command_stats(args: argparse.Namespace) -> int:
    _, runs_path = state_paths(args.state_dir.expanduser())
    runs = read_runs(runs_path)
    kinds = sorted({str(run.get("task_class")) for run in runs if run.get("task_class")})
    if not kinds:
        print("No runs recorded yet.")
        return 0
    print(f"Last {len(runs)} runs\n")
    for kind in kinds:
        print(kind)
        for route in ("cursor_api", "codex"):
            stats = route_stats(runs, kind, route)
            print(f"  {route}: {stats['runs']} runs; median cost {format_usd(stats['median_cost_usd'])}; median time {format_number(stats['median_elapsed_minutes'], 'min')}; acceptance {format_percent(stats['acceptance_rate'])}")
    return 0


def format_usd(value: float | None) -> str:
    return "not configured" if value is None else f"${value:.2f}"


def format_number(value: float | None, unit: str) -> str:
    return "no data" if value is None else f"{value:g} {unit}"


def format_percent(value: float | None) -> str:
    return "no data" if value is None else f"{value:.0%}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="abr", description="Agent Budget Router daily CLI")
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR, help="Defaults to ~/.agent-budget-router")
    commands = parser.add_subparsers(dest="command", required=True)
    route = commands.add_parser("route", help="Recommend a route before starting work")
    route.add_argument("task")
    route.add_argument("--path-hint", action="append", dest="path_hints", default=[])
    route.add_argument("--skill-count", type=int, default=0)
    route.add_argument("--no-codex-probe", action="store_true")
    route.add_argument("--json", action="store_true")
    route.set_defaults(handler=command_route)
    record = commands.add_parser("record", help="Store compact post-run facts; no prompt or transcript is stored")
    record.add_argument("--task-class", required=True)
    record.add_argument("--route", required=True, choices=("cursor_api", "codex"))
    record.add_argument("--completion", required=True, choices=("completed", "blocked", "failed"))
    record.add_argument("--acceptance", default="unknown", choices=("satisfied", "unsatisfied", "unknown"))
    record.add_argument("--elapsed-minutes", type=float)
    record.add_argument("--cost-usd", type=float)
    record.add_argument("--credit-units", type=float)
    record.add_argument("--tests", default="not_run", choices=("passed", "failed", "not_run"))
    record.add_argument("--lint", default="not_run", choices=("passed", "failed", "not_run"))
    record.add_argument("--build", default="not_run", choices=("passed", "failed", "not_run"))
    record.add_argument("--human-revisions", type=int, default=0)
    record.set_defaults(handler=command_record)
    configure = commands.add_parser("configure", help="Store current Cursor API rates once in local state")
    configure.add_argument("--input-rate", required=True, type=float, help="USD per million uncached input tokens")
    configure.add_argument("--cached-input-rate", required=True, type=float, help="USD per million cached input tokens")
    configure.add_argument("--output-rate", required=True, type=float, help="USD per million output tokens")
    configure.add_argument("--cached-input-ratio", type=float, default=0.0, help="Expected cached-input fraction (0-1)")
    configure.set_defaults(handler=command_configure)
    capture = commands.add_parser("capture-codex", help="Capture current Codex allowance and global usage summary")
    capture.set_defaults(handler=command_capture_codex)
    stats = commands.add_parser("stats", help="Show medians by task class and route")
    stats.set_defaults(handler=command_stats)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
