"""Reference extraction and provider selection for the Skill v1 path."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from linear_resolver import LinearResolver, Resolution


ISSUE_PATTERN = re.compile(r"(?<![A-Z0-9])([A-Z][A-Z0-9]+-\d+)(?![A-Z0-9])", re.IGNORECASE)


class ProviderResolver(Protocol):
    def resolve(self, identifier: str) -> Resolution: ...


@dataclass(frozen=True)
class ContextResolution:
    references: list[dict[str, str]]
    task_context: dict[str, Any] | None
    source_identity: dict[str, str] | None
    resolution_status: str


class ReferenceResolver:
    def __init__(self, providers: dict[str, ProviderResolver] | None = None) -> None:
        self._providers = providers if providers is not None else {"linear": LinearResolver()}

    def resolve(self, prompt: str) -> ContextResolution:
        match = ISSUE_PATTERN.search(prompt)
        if not match:
            return ContextResolution([], None, None, "NO_REFERENCE")
        identifier = match.group(1).upper()
        provider = self._providers.get("linear")
        if provider is None:
            reference = {"type": "issue", "provider": "linear", "id": identifier,
                         "resolution_status": "UNRESOLVED"}
            return ContextResolution([reference], None, None, "UNRESOLVED")
        resolved = provider.resolve(identifier)
        status = resolved.reference["resolution_status"]
        return ContextResolution(
            [resolved.reference], resolved.task_context, resolved.source_identity, status,
        )
