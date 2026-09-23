"""Contract tests for the Cursor Hook → common Host Adapter PoC."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import host_adapter  # noqa: E402
from linear_resolver import LinearResolver, Resolution  # noqa: E402


class ResolvedLinear:
    def resolve(self, identifier):
        assert identifier == "MY-172"
        return Resolution(
            reference={
                "type": "issue", "provider": "linear", "id": identifier,
                "resolution_status": "RESOLVED",
            },
            task_context={
                "title": "Portable visual direction skill",
                "summary": "Create a reusable skill across multiple hosts.",
                "acceptance_criteria": ["Verify more than one image model"],
                "path_hints": [],
                "related_links": [],
            },
        )


class UnresolvedLinear:
    def resolve(self, identifier):
        return Resolution(
            reference={
                "type": "issue", "provider": "linear", "id": identifier,
                "resolution_status": "UNRESOLVED",
            },
            task_context=None,
        )


def test_small_task_skips_without_detailed_preflight(monkeypatch):
    monkeypatch.setattr(
        host_adapter, "route_preflight",
        lambda *_: (_ for _ in ()).throw(AssertionError("must not route")),
    )

    result = host_adapter.evaluate_request({
        "prompt": "READMEの誤字修正して", "prompt_available": True,
    })

    assert result["decision"] == "SKIP"
    assert result["state"] == "READY"
    assert result["execution_policy"] == "DIRECT"
    assert result["forward"]["allowed"] is True


def test_confirm_first_is_not_forwarded_until_approved(monkeypatch):
    monkeypatch.setattr(host_adapter, "route_preflight", lambda *_: {
        "task_class": "feature_build", "estimated_context": {"min": 1, "max": 2},
        "estimated_generation": {"min": 1, "max": 2},
        "execution_policy": "CONFIRM_FIRST", "gate": {"level": "CONFIRM", "action": "ASK_USER"},
    })
    result = host_adapter.evaluate_request({
        "prompt": "MY-172を実装して", "prompt_available": True,
    }, linear_resolver=ResolvedLinear())

    assert result["state"] == "NEEDS_CONFIRMATION"
    assert result["forward"]["allowed"] is False
    approved = host_adapter.approve(result)
    assert approved["state"] == "READY"
    assert approved["forward"]["allowed"] is True


def test_blocked_state_cannot_be_forwarded():
    with pytest.raises(ValueError, match="BLOCKED requires forward.allowed=false"):
        host_adapter.validate_contract({
            "state": "BLOCKED", "execution_policy": "DEFER", "forward": {"allowed": True},
        })


def test_resolved_linear_context_is_passed_to_core(monkeypatch):
    captured = {}

    def capture_should_preflight(prompt, task_context):
        captured["prompt"] = prompt
        captured["task_context"] = task_context
        return {"decision": "PREFLIGHT", "reason": "cross_cutting"}

    monkeypatch.setattr(host_adapter, "should_preflight", capture_should_preflight)
    monkeypatch.setattr(host_adapter, "route_preflight", lambda *_: {
        "task_class": "feature_build", "estimated_context": {"min": 1, "max": 2},
        "estimated_generation": {"min": 1, "max": 2},
        "execution_policy": "CONFIRM_FIRST", "gate": {"level": "CONFIRM", "action": "ASK_USER"},
    })

    result = host_adapter.evaluate_request({
        "prompt": "MY-172を実装して", "prompt_available": True,
    }, linear_resolver=ResolvedLinear())

    assert result["resolution_status"] == "RESOLVED"
    assert captured["task_context"]["title"] == "Portable visual direction skill"
    assert "MY-172" in captured["prompt"]


def test_unresolved_linear_reference_uses_default_ask_policy():
    result = host_adapter.evaluate_request({
        "prompt": "MY-172を実装して", "prompt_available": True,
    }, linear_resolver=UnresolvedLinear())

    assert result["decision"] == "INPUT_UNAVAILABLE"
    assert result["resolution_status"] == "UNRESOLVED"
    assert result["state"] == "NEEDS_CONFIRMATION"
    assert result["execution_policy"] == "CONFIRM_FIRST"
    assert result["forward"]["allowed"] is False


def test_linear_resolver_normalizes_issue_without_persisting_its_body():
    payload = {
        "result": {
            "issue": {
                "identifier": "MY-172",
                "title": "Portable visual direction skill",
                "description": "Create a portable skill. https://example.test/reference",
                "url": "https://linear.app/example/MY-172",
            }
        }
    }

    def run_command(*_args, **_kwargs):
        return subprocess.CompletedProcess([], 0, json.dumps(payload), "")

    resolution = LinearResolver(run_command=run_command).resolve("MY-172")

    assert resolution.reference["resolution_status"] == "RESOLVED"
    assert resolution.task_context == {
        "title": "Portable visual direction skill",
        "summary": "Create a portable skill. https://example.test/reference",
        "acceptance_criteria": [],
        "path_hints": [],
        "related_links": [
            "https://linear.app/example/MY-172",
            "https://example.test/reference",
        ],
    }
