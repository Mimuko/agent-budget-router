"""PoC Linear resolver. Provider access is intentionally outside ABR Core."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Callable


RunCommand = Callable[..., subprocess.CompletedProcess[str]]
URL_PATTERN = re.compile(r"https?://[^\s)>]+")


@dataclass(frozen=True)
class Resolution:
    reference: dict[str, str]
    task_context: dict[str, Any] | None


class LinearResolver:
    """Resolve Linear issues through Orca's authenticated Linear CLI bridge."""

    def __init__(self, run_command: RunCommand = subprocess.run) -> None:
        self._run_command = run_command

    def resolve(self, identifier: str) -> Resolution:
        try:
            completed = self._run_command(
                ["orca", "linear", "issue", identifier, "--full", "--json"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=10,
            )
            if completed.returncode != 0:
                return self._unresolved(identifier)
            payload = json.loads(completed.stdout)
            issue = payload.get("result", {}).get("issue")
            if not isinstance(issue, dict) or issue.get("identifier") != identifier:
                return self._unresolved(identifier)
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError, TypeError, ValueError):
            return self._unresolved(identifier)

        description = issue.get("description") if isinstance(issue.get("description"), str) else ""
        title = issue.get("title") if isinstance(issue.get("title"), str) else ""
        related_links = [issue["url"]] if isinstance(issue.get("url"), str) else []
        related_links.extend(URL_PATTERN.findall(description))
        return Resolution(
            reference={
                "type": "issue",
                "provider": "linear",
                "id": identifier,
                "resolution_status": "RESOLVED",
            },
            task_context={
                "title": title,
                "summary": description[:2000],
                "acceptance_criteria": [],
                "path_hints": [],
                "related_links": list(dict.fromkeys(related_links)),
            },
        )

    @staticmethod
    def _unresolved(identifier: str) -> Resolution:
        return Resolution(
            reference={
                "type": "issue",
                "provider": "linear",
                "id": identifier,
                "resolution_status": "UNRESOLVED",
            },
            task_context=None,
        )
