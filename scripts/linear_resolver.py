"""Linear normalization behind an injectable, read-only backend."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from linear_backend import BackendError, LinearBackend, OrcaLinearBackend, RunCommand


URL_PATTERN = re.compile(r"https?://[^\s)>]+")


@dataclass(frozen=True)
class Resolution:
    reference: dict[str, str]
    task_context: dict[str, Any] | None
    source_identity: dict[str, str] | None = None


class LinearResolver:
    """Normalize fetched Linear source without task or budget decisions."""

    def __init__(
        self, backend: LinearBackend | None = None, *, run_command: RunCommand | None = None,
    ) -> None:
        if backend is not None and run_command is not None:
            raise ValueError("provide backend or run_command, not both")
        self._backend = backend or (
            OrcaLinearBackend(run_command=run_command) if run_command is not None else OrcaLinearBackend()
        )

    def resolve(self, identifier: str) -> Resolution:
        outcome = self._backend.fetch_issue(identifier)
        if isinstance(outcome, BackendError):
            if outcome.code == "partial":
                return Resolution(self._reference(identifier, "PARTIALLY_RESOLVED"), None)
            return self._unresolved(identifier)
        issue = outcome.fields
        if issue.get("identifier") != identifier:
            return self._unresolved(identifier)
        title = issue.get("title") if isinstance(issue.get("title"), str) else ""
        description = issue.get("description") if isinstance(issue.get("description"), str) else ""
        url = issue.get("url") if isinstance(issue.get("url"), str) else ""
        if not title:
            return Resolution(self._reference(identifier, "PARTIALLY_RESOLVED"), None)
        source = {
            "native_id": issue.get("id") if isinstance(issue.get("id"), str) else identifier,
            "identifier": identifier,
            "title": title,
            "description": description,
            "url": url,
            "revision": issue.get("updatedAt") if isinstance(issue.get("updatedAt"), str) else "",
        }
        digest = hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        links = [url] if url else []
        links.extend(URL_PATTERN.findall(description))
        return Resolution(
            reference=self._reference(identifier, "RESOLVED"),
            task_context={
                "title": title,
                "summary": description[:2000],
                "acceptance_criteria": [],
                "path_hints": [],
                "related_links": list(dict.fromkeys(links)),
            },
            source_identity={
                "provider": "linear", "native_id": source["native_id"],
                "identifier": identifier, "revision": source["revision"] or digest,
                "canonical_source_digest": digest,
            },
        )

    @staticmethod
    def _reference(identifier: str, status: str) -> dict[str, str]:
        return {"type": "issue", "provider": "linear", "id": identifier, "resolution_status": status}

    @classmethod
    def _unresolved(cls, identifier: str) -> Resolution:
        return Resolution(cls._reference(identifier, "UNRESOLVED"), None)
