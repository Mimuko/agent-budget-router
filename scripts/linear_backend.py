"""Read-only Linear backend interface and development Orca fallback."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class BackendIssue:
    fields: dict[str, Any]


@dataclass(frozen=True)
class BackendError:
    code: str


class LinearBackend(Protocol):
    def fetch_issue(self, identifier: str) -> BackendIssue | BackendError: ...


RunCommand = Callable[..., subprocess.CompletedProcess[str]]


class OrcaLinearBackend:
    """Development fallback; the common resolver never runs the Orca CLI."""

    def __init__(self, run_command: RunCommand = subprocess.run) -> None:
        self._run_command = run_command

    def fetch_issue(self, identifier: str) -> BackendIssue | BackendError:
        try:
            completed = self._run_command(
                ["orca", "linear", "issue", identifier, "--full", "--json"],
                check=False, capture_output=True, text=True, encoding="utf-8", timeout=10,
            )
            payload = json.loads(completed.stdout)
            if completed.returncode != 0 or payload.get("ok") is False:
                code = str((payload.get("error") or {}).get("code", "")).lower()
                if "not_found" in code:
                    return BackendError("not_found")
                if "auth" in code or "permission" in code:
                    return BackendError("auth_unavailable")
                if "partial" in code:
                    return BackendError("partial")
                return BackendError("network_error")
            issue = payload.get("result", {}).get("issue")
            if not isinstance(issue, dict) or issue.get("identifier") != identifier:
                return BackendError("not_found")
            return BackendIssue(issue)
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError, TypeError, ValueError):
            return BackendError("network_error")
