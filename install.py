"""Install the distribution's shared core and host shims at user scope."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path


MARKER = ".abr-managed.json"
NAMES = ("core", "cursor", "codex")


def paths(home: Path) -> dict[str, Path]:
    return {
        "core": home / ".agent-budget-router" / "agent-budget-router",
        "cursor": home / ".cursor" / "skills" / "agent-budget-router",
        "codex": home / ".agents" / "skills" / "agent-budget-router",
    }


def managed(path: Path) -> bool:
    if path.is_symlink():
        return False
    try:
        return json.loads((path / MARKER).read_text(encoding="utf-8"))["manager"] == "abr-user-installer-v1"
    except (OSError, ValueError, KeyError, TypeError):
        return False


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"backups": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def stage(source: Path, core: Path, staging: Path) -> None:
    if not (source / "scripts" / "skill_orchestrator.py").is_file():
        raise RuntimeError("source is missing the ABR core")
    for host in ("cursor", "codex"):
        shim = source / "host-shims" / host
        if not (shim / "SKILL.md").is_file() or not (shim / f"{host}_adapter.py").is_file():
            raise RuntimeError(f"source is missing the {host} shim")
    shutil.copytree(source, staging / "core", ignore=shutil.ignore_patterns(".git", ".sessions", "__pycache__", "*.pyc"))
    for host in ("cursor", "codex"):
        target = staging / host
        target.mkdir()
        shutil.copy2(source / "host-shims" / host / "SKILL.md", target / "SKILL.md")
        (target / "scripts").mkdir()
        for script in (source / "host-shims" / host).glob("*.py"):
            shutil.copy2(script, target / "scripts" / script.name)
        if host == "codex":
            (target / "agents").mkdir()
            shutil.copy2(source / "host-shims" / host / "openai.yaml", target / "agents" / "openai.yaml")
        (target / ".abr-core-path").write_text(str(core.resolve()) + "\n", encoding="utf-8")
    for name in NAMES:
        (staging / name / MARKER).write_text(
            json.dumps({"manager": "abr-user-installer-v1", "component": name}) + "\n", encoding="utf-8"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "update", "uninstall", "rollback"), nargs="?", default="install")
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--home", type=Path, default=Path.home())
    args = parser.parse_args()
    home = args.home.expanduser().resolve()
    source = args.source.expanduser().resolve()
    targets = paths(home)
    state_file = home / ".agent-budget-router" / "installer-state.json"
    state = load_state(state_file)
    existing = {name: target.exists() or target.is_symlink() for name, target in targets.items()}
    for name, target in targets.items():
        if existing[name] and not managed(target):
            raise RuntimeError(f"refusing to replace unmanaged {name}: {target}")
    if args.action == "rollback" and not state["backups"]:
        raise RuntimeError("no previous installation to restore")
    if args.action == "update" and not all(existing.values()):
        raise RuntimeError("update requires an existing complete installation; use install")
    if args.action == "uninstall" and not any(existing.values()):
        print("ABR is already uninstalled")
        return 0
    if args.action == "rollback":
        backup = Path(state["backups"][-1])
        for name in NAMES:
            previous = backup / name
            if previous.exists() and not managed(previous):
                raise RuntimeError(f"backup is invalid: {previous}")
    else:
        backup = home / ".agent-budget-router" / "backups" / uuid.uuid4().hex
    current_backup = (
        home / ".agent-budget-router" / "backups" / uuid.uuid4().hex
        if args.action == "rollback" else backup
    )
    staging = Path(tempfile.mkdtemp(prefix="abr-stage-", dir=home))
    moved_old: list[str] = []
    moved_new: list[str] = []
    try:
        if args.action in ("install", "update"):
            stage(source, targets["core"], staging)
        current_backup.mkdir(parents=True, exist_ok=True)
        for name, target in targets.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            if existing[name]:
                target.rename(current_backup / name)
                moved_old.append(name)
        if args.action in ("install", "update", "rollback"):
            for name, target in targets.items():
                candidate = (staging if args.action != "rollback" else backup) / name
                if candidate.exists():
                    candidate.rename(target)
                    moved_new.append(name)
        if args.action == "rollback":
            state["backups"].pop()
            backup.rmdir()
            if moved_old:
                state["backups"].append(str(current_backup))
        elif moved_old:
            state["backups"].append(str(backup))
        else:
            current_backup.rmdir()
        save_state(state_file, state)
    except Exception:
        for name in moved_new:
            target = targets[name]
            if target.exists():
                shutil.rmtree(target)
        for name in moved_old:
            previous = current_backup / name
            if previous.exists():
                previous.rename(targets[name])
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print(f"ABR {args.action} complete: " + ", ".join(f"{name}={target}" for name, target in targets.items()))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
