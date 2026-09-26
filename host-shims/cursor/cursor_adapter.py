"""Cursor-only invocation adapter for the shared Skill v1 Orchestrator."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_POLICY = {"input_unavailable": "ask", "reference_unresolved": "ask"}


def _repo_root() -> Path:
    pointer = Path(__file__).resolve().parent.parent / ".abr-core-path"
    if pointer.is_file():
        core = Path(pointer.read_text(encoding="utf-8").strip())
        if (core / "scripts" / "skill_orchestrator.py").is_file():
            return core.parent
        raise RuntimeError(f"installed ABR core is missing: {core}")
    for parent in Path(__file__).resolve().parents:
        if (parent / "agent-budget-router" / "scripts" / "skill_orchestrator.py").is_file():
            return parent
    raise RuntimeError("could not locate agent-plugins root from Cursor Skill")


def _request(task: str, cwd: Path) -> dict[str, Any]:
    lookup = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=cwd,
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    repository_scope = lookup.stdout.strip() if lookup.returncode == 0 else str(cwd)
    return {
        "schema_version": "skill-v1",
        "prompt": task,
        "prompt_available": bool(task.strip()),
        "references": [],
        "workspace_scope": str(cwd),
        "repository_scope": repository_scope,
        "policy": dict(DEFAULT_POLICY),
    }


def _orchestrator() -> Path:
    return _repo_root() / "agent-budget-router" / "scripts" / "skill_orchestrator.py"


def _scripts_dir() -> Path:
    return _repo_root() / "agent-budget-router" / "scripts"


def _emit_result(result: dict[str, Any]) -> int:
    """Write diagnostics then human summary (or violation) to stderr; JSON to stdout."""
    scripts = str(_scripts_dir())
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from human_summary import (
        ensure_utf8_stdio,
        format_human_summary,
        missing_required_fields,
    )

    ensure_utf8_stdio()
    missing = missing_required_fields(result)
    forward = result.get("forward") if isinstance(result.get("forward"), dict) else {}

    diagnostic = {
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "adapter": str(Path(__file__).resolve()),
        "orchestrator": str(_orchestrator()),
        "decision": result.get("decision"),
        "state": result.get("state"),
        "execution_policy": result.get("execution_policy"),
        "forward_allowed": forward.get("allowed"),
        "error": result.get("error"),
    }
    trace_file = Path(__file__).resolve().parent.parent / "invocation-diagnostics.jsonl"
    with trace_file.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(diagnostic, ensure_ascii=True) + "\n")
    print(f"cursor-skill-adapter: {trace_file}", file=sys.stderr, flush=True)

    if missing or "error" in result:
        if missing:
            print(
                "contract violation: missing required field(s): " + ", ".join(missing),
                file=sys.stderr,
                flush=True,
            )
        print(json.dumps(result, ensure_ascii=True), flush=True)
        return 2

    print(format_human_summary(result), end="", file=sys.stderr, flush=True)
    print(json.dumps(result, ensure_ascii=True), flush=True)
    return 0


def _write_result(line: str) -> tuple[dict[str, Any], int]:
    result = json.loads(line)
    if not isinstance(result, dict):
        raise ValueError("Orchestrator result must be a JSON object")
    return result, _emit_result(result)


def _child_env(linear_backend: str | None) -> dict[str, str]:
    env = os.environ.copy()
    if linear_backend is not None:
        env["ABR_LINEAR_BACKEND"] = linear_backend
    return env


def _sessions_dir() -> Path:
    return Path(__file__).resolve().parent.parent / ".sessions"


def _await_json(path: Path, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("Cursor session response must be a JSON object")
            return value
        time.sleep(0.1)
    raise RuntimeError(f"Cursor session timed out waiting for {path.name}")


def start_persistent_session(request: dict[str, Any], linear_backend: str | None) -> int:
    session_id = uuid.uuid4().hex
    state_dir = _sessions_dir() / session_id
    state_dir.mkdir(parents=True)
    (state_dir / "configuration.json").write_text(json.dumps({
        "request": request, "linear_backend": linear_backend,
    }, ensure_ascii=True), encoding="utf-8")
    worker = Path(__file__).with_name("cursor_session_worker.py")
    subprocess.Popen(
        [sys.executable, str(worker), str(state_dir)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        start_new_session=sys.platform != "win32",
    )
    initial = _await_json(state_dir / "initial.json", 30)
    print(f"cursor-session-id: {session_id}", file=sys.stderr, flush=True)
    _, code = _write_result(json.dumps(initial, ensure_ascii=True))
    return code


def resume_persistent_session(session_id: str, request: dict[str, Any], approved: bool) -> int:
    if len(session_id) != 32 or any(character not in "0123456789abcdef" for character in session_id):
        raise ValueError("invalid Cursor session id")
    state_dir = _sessions_dir() / session_id
    if not (state_dir / "initial.json").is_file():
        raise ValueError("Cursor session is unavailable")
    command_id = uuid.uuid4().hex
    command = {"id": command_id, "request": request, "approved": approved}
    temporary = state_dir / f"command-{command_id}.tmp"
    temporary.write_text(json.dumps(command, ensure_ascii=True), encoding="utf-8")
    temporary.replace(state_dir / f"command-{command_id}.json")
    result = _await_json(state_dir / f"response-{command_id}.json", 30)
    _, code = _write_result(json.dumps(result, ensure_ascii=True))
    return code


def run_once(request: dict[str, Any], linear_backend: str | None) -> int:
    completed = subprocess.run(
        [sys.executable, str(_orchestrator())],
        input=json.dumps(request, ensure_ascii=True),
        capture_output=True, text=True, encoding="utf-8", check=False,
        env=_child_env(linear_backend),
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr)
        return completed.returncode
    _, code = _write_result(completed.stdout)
    return code


def run_session(
    request: dict[str, Any], linear_backend: str | None,
    approved: bool | None, repeat_approval: bool,
) -> int:
    child = subprocess.Popen(
        [sys.executable, str(_orchestrator()), "--session"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None,
        text=True, encoding="utf-8", bufsize=1, env=_child_env(linear_backend),
    )
    assert child.stdin is not None and child.stdout is not None
    try:
        child.stdin.write(json.dumps({"action": "start", "request": request}, ensure_ascii=True) + "\n")
        child.stdin.flush()
        first_line = child.stdout.readline()
        if not first_line:
            return child.wait() or 1
        initial, code = _write_result(first_line)
        if code != 0:
            child.stdin.close()
            child.wait()
            return code
        if initial.get("state") != "NEEDS_CONFIRMATION":
            child.stdin.close()
            return child.wait()

        if approved is None:
            approval_line = sys.stdin.readline()
            if not approval_line:
                return 2
            approval = json.loads(approval_line)
            if not isinstance(approval, dict) or not isinstance(approval.get("approved"), bool):
                raise ValueError("Cursor shim input must be JSON with boolean approved")
            approved = approval["approved"]

        def resume() -> tuple[dict[str, Any], int]:
            child.stdin.write(json.dumps({
                "action": "resume", "request": request, "approved": approved,
            }, ensure_ascii=True) + "\n")
            child.stdin.flush()
            resumed_line = child.stdout.readline()
            if not resumed_line:
                raise RuntimeError("Orchestrator closed before resume result")
            return _write_result(resumed_line)

        resumed, resume_code = resume()
        if repeat_approval:
            repeated, _ = resume()
            child.stdin.close()
            child.wait()
            return 0 if "error" in repeated and resumed.get("state") == "READY" else 2
        child.stdin.close()
        child.wait()
        if resume_code != 0:
            return resume_code
        return 0 if resumed.get("forward", {}).get("allowed") is not True or resumed.get("state") == "READY" else 2
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, help="Natural-language task from the explicit Cursor Skill invocation")
    parser.add_argument("--session", action="store_true", help="Keep one confirmation workflow alive")
    parser.add_argument("--start-session", action="store_true", help="Start a persistent confirmation workflow for Cursor chat")
    parser.add_argument("--resume-session", metavar="ID", help="Resume a persistent Cursor confirmation workflow")
    parser.add_argument("--linear-backend", choices=("orca",), help="Explicit PoC Linear backend")
    parser.add_argument("--approved", choices=("true", "false"), help="Forward an approval already given in the Cursor conversation")
    parser.add_argument("--repeat-approval", action="store_true", help="Diagnose rejection of the same approval sent twice")
    args = parser.parse_args()
    try:
        if sum((args.session, args.start_session, args.resume_session is not None)) > 1:
            raise ValueError("choose one session mode")
        if args.start_session and (args.approved is not None or args.repeat_approval):
            raise ValueError("start-session cannot include approval")
        if args.resume_session is not None and (args.approved is None or args.repeat_approval):
            raise ValueError("resume-session requires --approved and cannot repeat automatically")
        if (args.approved is not None or args.repeat_approval) and not args.session:
            if args.resume_session is None:
                raise ValueError("approval options require a session")
        if args.repeat_approval and args.approved is None:
            raise ValueError("--repeat-approval requires --approved")
        request = _request(args.task, Path.cwd().resolve())
        if args.start_session:
            return start_persistent_session(request, args.linear_backend)
        if args.resume_session is not None:
            return resume_persistent_session(args.resume_session, request, args.approved == "true")
        if args.session:
            approved = None if args.approved is None else args.approved == "true"
            return run_session(request, args.linear_backend, approved, args.repeat_approval)
        return run_once(request, args.linear_backend)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"cursor-agent-budget-router: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
