"""Keep one shared Orchestrator session alive across Cursor chat turns."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from cursor_adapter import _child_env, _orchestrator


def _write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=True), encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    state_dir = Path(sys.argv[1])
    configuration = json.loads((state_dir / "configuration.json").read_text(encoding="utf-8"))
    child = subprocess.Popen(
        [sys.executable, str(_orchestrator()), "--session"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding="utf-8", bufsize=1,
        env=_child_env(configuration["linear_backend"]),
    )
    assert child.stdin is not None and child.stdout is not None
    try:
        child.stdin.write(json.dumps({"action": "start", "request": configuration["request"]}, ensure_ascii=True) + "\n")
        child.stdin.flush()
        line = child.stdout.readline()
        _write_json(state_dir / "initial.json", json.loads(line) if line else {"error": "Orchestrator closed before start result"})
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline and child.poll() is None:
            commands = sorted(state_dir.glob("command-*.json"))
            if not commands:
                time.sleep(0.1)
                continue
            command_file = commands[0]
            command = json.loads(command_file.read_text(encoding="utf-8"))
            child.stdin.write(json.dumps({
                "action": "resume", "request": command["request"], "approved": command["approved"],
            }, ensure_ascii=True) + "\n")
            child.stdin.flush()
            line = child.stdout.readline()
            result = json.loads(line) if line else {"error": "Orchestrator closed before resume result"}
            _write_json(state_dir / f"response-{command['id']}.json", result)
            command_file.unlink()
            if "error" in result:
                break
            deadline = time.monotonic() + 120
        return 0
    finally:
        if child.poll() is None:
            child.kill()
        child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
