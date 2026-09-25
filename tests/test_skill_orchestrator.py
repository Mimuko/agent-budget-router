"""Skill v1 orchestration and Resolver boundary tests."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import linear_backend  # noqa: E402
import skill_orchestrator  # noqa: E402
from linear_backend import BackendError, BackendIssue  # noqa: E402
from linear_resolver import LinearResolver  # noqa: E402
from reference_resolver import ContextResolution, ReferenceResolver  # noqa: E402


class NoReference:
    def resolve(self, _prompt):
        return ContextResolution([], None, None, "NO_REFERENCE")


class ResolvedReference:
    def resolve(self, _prompt):
        return ContextResolution(
            [{"type": "issue", "provider": "linear", "id": "MY-172", "resolution_status": "RESOLVED"}],
            {"title": "A feature", "summary": "Update several modules", "acceptance_criteria": [], "path_hints": []},
            {"provider": "linear", "native_id": "secret-source-id", "revision": "revision"},
            "RESOLVED",
        )


def test_skip_and_unavailable_do_not_estimate_or_route(monkeypatch):
    monkeypatch.setattr(skill_orchestrator, "estimate_task", lambda *_: (_ for _ in ()).throw(AssertionError("must not estimate")))
    monkeypatch.setattr(skill_orchestrator, "route", lambda *_: (_ for _ in ()).throw(AssertionError("must not route")))
    skip = skill_orchestrator.evaluate_request(
        {"prompt": "READMEの誤字修正して", "prompt_available": True}, resolver=NoReference(),
    )
    missing = skill_orchestrator.evaluate_request(
        {"prompt": "", "prompt_available": False}, resolver=NoReference(),
    )
    assert (skip["decision"], skip["state"], skip["execution_policy"]) == ("SKIP", "READY", "DIRECT")
    assert (missing["decision"], missing["state"], missing["execution_policy"]) == (
        "INPUT_UNAVAILABLE", "NEEDS_CONFIRMATION", "CONFIRM_FIRST",
    )


def test_preflight_estimates_once_and_passes_same_task_estimate(monkeypatch):
    events = []
    task = {
        "task_class": "feature_build", "estimated_context": {"min": 1, "max": 2},
        "estimated_generation": {"min": 3, "max": 4}, "base_recommendation": "DIRECT",
        "base_reason": "feature_build",
    }

    def estimate(prompt, context):
        events.append("estimate")
        assert prompt == "MY-172を実装して"
        assert context["title"] == "A feature"
        return task

    class BudgetEstimator:
        def estimate(self, received):
            events.append("budget")
            assert received is task
            return {"remaining_ratio": 0.5, "estimated_task_ratio": 0.3,
                    "snapshot_at": "2026-09-24T02:00:00Z", "scope": "account"}

    def route(received, budget):
        events.append("route")
        assert received is task
        assert "source_identity" not in received
        assert budget["estimated_task_ratio"] == 0.3
        return {**received, "recommended_policy": "SPLIT", "recommendation_reason": "budget_limited"}

    monkeypatch.setattr(skill_orchestrator, "estimate_task", estimate)
    monkeypatch.setattr(skill_orchestrator, "route", route)
    result = skill_orchestrator.evaluate_request(
        {"prompt": "MY-172を実装して", "prompt_available": True},
        resolver=ResolvedReference(), budget_estimator=BudgetEstimator(),
    )
    assert events == ["estimate", "budget", "route"]
    assert result["reason"] == "medium_task"
    assert result["preflight"]["base_reason"] == "feature_build"
    assert result["preflight"]["recommendation_reason"] == "budget_limited"
    assert (result["state"], result["execution_policy"], result["forward"]["allowed"]) == (
        "NEEDS_CONFIRMATION", "CONFIRM_FIRST", False,
    )
    assert result["preflight"]["recommended_policy"] == "SPLIT"


def test_linear_backend_injection_normalizes_source_identity():
    class FakeBackend:
        def fetch_issue(self, identifier):
            assert identifier == "MY-172"
            return BackendIssue({
                "id": "native-id", "identifier": identifier, "title": "Feature",
                "description": "Implement feature. https://example.test/spec",
                "url": "https://linear.app/issue/MY-172", "updatedAt": "2026-09-24T00:00:00Z",
            })

    resolved = ReferenceResolver({"linear": LinearResolver(backend=FakeBackend())}).resolve(
        "MY-172を実装して"
    )
    assert resolved.resolution_status == "RESOLVED"
    assert resolved.task_context["title"] == "Feature"
    assert resolved.source_identity["native_id"] == "native-id"
    assert resolved.source_identity["revision"] == "2026-09-24T00:00:00Z"
    assert len(resolved.source_identity["canonical_source_digest"]) == 64
    assert resolved.task_context["related_links"] == [
        "https://linear.app/issue/MY-172", "https://example.test/spec",
    ]


def test_default_resolvers_leave_linear_unresolved_without_orca_cli(monkeypatch):
    def must_not_run(*_args, **_kwargs):
        raise AssertionError("default resolver must not call Orca CLI")

    monkeypatch.setattr(linear_backend.subprocess, "run", must_not_run)
    monkeypatch.setattr(linear_backend.OrcaLinearBackend, "fetch_issue", must_not_run)
    direct = LinearResolver().resolve("MY-172")
    reference = ReferenceResolver().resolve("MY-172を実装して")

    assert direct.reference["resolution_status"] == "UNRESOLVED"
    assert direct.task_context is None
    assert reference.resolution_status == "UNRESOLVED"
    assert reference.task_context is None
    assert reference.source_identity is None


def test_reference_resolver_skips_backend_without_reference():
    class MustNotFetch:
        def resolve(self, _identifier):
            raise AssertionError("must not fetch")

    resolved = ReferenceResolver({"linear": MustNotFetch()}).resolve("READMEの誤字修正して")
    assert resolved.resolution_status == "NO_REFERENCE"
    assert resolved.references == []


def test_partial_backend_result_does_not_create_task_context():
    class PartialBackend:
        def fetch_issue(self, _identifier):
            return BackendError("partial")

    resolved = ReferenceResolver({"linear": LinearResolver(backend=PartialBackend())}).resolve(
        "MY-172を実装して"
    )
    assert resolved.resolution_status == "PARTIALLY_RESOLVED"
    assert resolved.task_context is None
    assert resolved.source_identity is None


def test_unavailable_budget_uses_base_reason_without_changing_workflow_reason(monkeypatch):
    task = {"task_class": "feature_build", "estimated_context": {"min": 1, "max": 2},
            "estimated_generation": {"min": 3, "max": 4}, "base_recommendation": "DIRECT",
            "base_reason": "feature_build"}
    monkeypatch.setattr(skill_orchestrator, "estimate_task", lambda *_: task)
    result = skill_orchestrator.evaluate_request(
        {"prompt": "MY-172を実装して", "prompt_available": True}, resolver=ResolvedReference(),
    )
    assert result["reason"] == "medium_task"
    assert result["preflight"]["base_reason"] == "feature_build"
    assert result["preflight"]["recommendation_reason"] == "budget_unavailable"
    assert result["execution_policy"] == "CONFIRM_FIRST"
    assert result["forward"]["allowed"] is False


def test_approval_re_resolves_same_request_and_returns_ready_once():
    class RevisionBackend:
        revision = "r1"

        def fetch_issue(self, identifier):
            return BackendIssue({
                "id": "native", "identifier": identifier, "title": "A sufficiently large feature",
                "description": "Update several components and verify behavior.",
                "url": "https://linear.app/issue/MY-172", "updatedAt": self.revision,
            })

    backend = RevisionBackend()
    workflow = skill_orchestrator.SkillWorkflow(
        resolver=ReferenceResolver({"linear": LinearResolver(backend=backend)}),
    )
    request = {"prompt": "MY-172を実装して", "prompt_available": True,
               "workspace_scope": "workspace-1", "repository_scope": "repo-1"}

    pending = workflow.start(request)
    assert pending["state"] == "NEEDS_CONFIRMATION"
    ready = workflow.resume(request, approved=True)
    assert (ready["state"], ready["forward"]["allowed"]) == ("READY", True)
    try:
        workflow.resume(request, approved=True)
    except ValueError as exc:
        assert "no pending confirmation" in str(exc)
    else:
        raise AssertionError("approval must be single-use")


def test_approval_is_rejected_when_linear_source_changes():
    class RevisionBackend:
        revision = "r1"

        def fetch_issue(self, identifier):
            return BackendIssue({
                "id": "native", "identifier": identifier, "title": "A sufficiently large feature",
                "description": "Update several components and verify behavior.",
                "url": "https://linear.app/issue/MY-172", "updatedAt": self.revision,
            })

    backend = RevisionBackend()
    workflow = skill_orchestrator.SkillWorkflow(
        resolver=ReferenceResolver({"linear": LinearResolver(backend=backend)}),
    )
    request = {"prompt": "MY-172を実装して", "prompt_available": True}
    assert workflow.start(request)["state"] == "NEEDS_CONFIRMATION"
    backend.revision = "r2"
    changed = workflow.resume(request, approved=True)
    assert changed["state"] == "NEEDS_CONFIRMATION"
    assert changed["forward"]["allowed"] is False


def test_jsonl_session_returns_shared_contract_for_start_and_approval():
    script = Path(skill_orchestrator.__file__)
    messages = [
        {"action": "start", "request": {"prompt": "MY-172を実装して", "prompt_available": True}},
        {"action": "resume", "request": {"prompt": "MY-172を実装して", "prompt_available": True}, "approved": True},
    ]
    completed = subprocess.run(
        [sys.executable, str(script), "--session"], input="\n".join(map(json.dumps, messages)) + "\n",
        text=True, capture_output=True, check=True,
    )
    initial, resumed = map(json.loads, completed.stdout.splitlines())
    assert (initial["decision"], initial["resolution_status"], initial["state"],
            initial["execution_policy"], initial["forward"]["allowed"]) == (
        "INPUT_UNAVAILABLE", "UNRESOLVED", "NEEDS_CONFIRMATION", "CONFIRM_FIRST", False,
    )
    assert (resumed["state"], resumed["execution_policy"], resumed["forward"]["allowed"]) == (
        "READY", "CONFIRM_FIRST", True,
    )
