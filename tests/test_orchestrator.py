"""Tests for the executable local proposal orchestrator."""

from __future__ import annotations

import re
from pathlib import Path

from scripts.orchestrator.codex import sanitized_agent_environment, validate_output
from scripts.orchestrator.config import load_config, select_model
from scripts.orchestrator.github import ProjectField, ProjectSnapshot
from scripts.orchestrator.model import CodexRun, IssueRef, ModelSelection, Usage
from scripts.orchestrator.proposal import ProposalWorkflow
from scripts.orchestrator.state import StateStore
from scripts.validate_repository import ROOT


class FakeAgent:
    """Return deterministic schema-shaped PM/BA results from requested identities."""

    def __init__(self) -> None:
        self.calls = 0

    def run(
        self,
        *,
        prompt: str,
        schema_path: Path,
        model: ModelSelection,
        timeout_seconds: int,
    ) -> CodexRun:
        self.calls += 1
        workflow_id = _match(prompt, r"workflow_id: (wf-[a-f0-9]+)")
        proposal_id = _match(prompt, r"proposal_id: (FP-[0-9]+)")
        version = int(_match(prompt, r"proposal_version: ([0-9]+)"))
        if schema_path.name == "feature-proposal.schema.json":
            output = {
                "schema_version": 1,
                "proposal_id": proposal_id,
                "proposal_version": version,
                "title": "Resume the learner's current lesson",
                "problem": "Returning learners need a reliable way to resume an interrupted lesson.",
                "target_users": ["Software professionals using short learning sessions"],
                "desired_outcome": (
                    "A returning learner can continue from the last confirmed learning position."
                ),
                "success_measures": [
                    {
                        "measure": "Successful resume attempts",
                        "target": None,
                        "measurement_window": None,
                    }
                ],
                "scope": {
                    "in": ["Open the last confirmed learning position"],
                    "out": ["Cross-device synchronization conflict resolution"],
                },
                "acceptance_criteria": [
                    {
                        "id": "AC-1",
                        "statement": "A returning learner can open the last confirmed lesson position.",
                        "verification": "Automated integration test and independent QA scenario",
                    }
                ],
                "risks": [],
                "dependencies": [],
                "decisions_required": [],
                "priority": "P1",
                "size": "S",
                "status": "proposed",
                "context_refs": ["docs/product/user-journeys.md"],
                "provenance": {
                    "workflow_id": workflow_id,
                    "role": "product_manager",
                    "agent_version": "fake-pm-1",
                    "generated_at": "2026-08-28T00:00:00Z",
                },
            }
        else:
            output = {
                "schema_version": 1,
                "workflow_id": workflow_id,
                "proposal_id": proposal_id,
                "proposal_version": version,
                "verdict": "accepted",
                "summary": "The proposal is bounded, unique and independently testable.",
                "duplicate_assessment": {"status": "no_duplicate", "evidence": []},
                "size_assessment": {
                    "status": "appropriate",
                    "suggested_size": "S",
                    "reason": "One bounded user-visible behaviour.",
                },
                "acceptance_criteria_results": [
                    {"criterion_id": "AC-1", "status": "testable", "feedback": ""}
                ],
                "decisions_required": [],
                "required_revisions": [],
                "context_refs": ["docs/product/user-journeys.md"],
                "provenance": {
                    "role": "business_analysis",
                    "agent_version": "fake-ba-1",
                    "generated_at": "2026-08-28T00:00:01Z",
                },
            }
        validate_output(output, schema_path)
        return CodexRun(
            output=output,
            usage=Usage(input_tokens=100, output_tokens=50, total_tokens=150),
            elapsed_ms=10,
            thread_id="fake-thread",
        )


class FakeGitHub:
    """In-memory GitHub control plane used to verify idempotent publication."""

    def __init__(self) -> None:
        self.issue: IssueRef | None = None
        self.issue_body = ""
        self.project_adds = 0
        self.field_values: dict[str, str | int] = {}
        self.comments: list[tuple[str, str]] = []
        fields = {
            "Status": _single("status", "Awaiting Human"),
            "Product Approval": _single("approval", "Pending"),
            "Type": _single("type", "Feature"),
            "Priority": _single("priority", "P1"),
            "Size": _single("size", "S"),
            "Current Role": _single("role", "Human"),
            "Automation State": _single("automation", "Waiting"),
            "Attempt Count": ProjectField("attempts", "NUMBER", {}),
            "Workflow ID": ProjectField("workflow", "TEXT", {}),
        }
        self.project = ProjectSnapshot("project-1", "https://github.com/users/test/projects/1", fields)

    def project_snapshot(self) -> ProjectSnapshot:
        return self.project

    def find_issue_by_marker(self, marker: str) -> IssueRef | None:
        return self.issue if marker in self.issue_body else None

    def create_issue(self, title: str, body: str) -> IssueRef:
        assert title
        self.issue_body = body
        self.issue = IssueRef(7, "issue-node-7", "https://github.com/test/repo/issues/7")
        return self.issue

    def add_to_project(self, project_id: str, issue_node_id: str) -> str:
        assert project_id == "project-1"
        assert issue_node_id == "issue-node-7"
        self.project_adds += 1
        return "item-1"

    def update_project_fields(
        self,
        project: ProjectSnapshot,
        item_id: str,
        values: dict[str, str | int],
    ) -> None:
        assert project.project_id == "project-1"
        assert item_id == "item-1"
        self.field_values.update(values)

    def find_comment_by_marker(self, issue_number: int, marker: str) -> str | None:
        assert issue_number == 7
        for url, body in self.comments:
            if marker in body:
                return url
        return None

    def add_comment(self, issue_number: int, body: str) -> str:
        assert issue_number == 7
        url = f"https://api.github.com/comments/{len(self.comments) + 1}"
        self.comments.append((url, body))
        return url


def _single(field_id: str, option: str) -> ProjectField:
    return ProjectField(field_id, "SINGLE_SELECT", {option: f"option-{field_id}"})


def _match(text: str, pattern: str) -> str:
    match = re.search(pattern, text)
    if match is None:
        raise AssertionError(f"prompt did not contain {pattern!r}")
    return match.group(1)


def configured(tmp_path: Path):  # type: ignore[no-untyped-def]
    """Load repository policy with local non-secret bootstrap identifiers."""
    return load_config(
        ROOT,
        {
            "GITHUB_PROJECT_NUMBER": "1",
            "GITHUB_PROJECT_URL": "https://github.com/users/test/projects/1",
            "GITHUB_AUTOMATION_LOGIN": "automation-test",
            "GITHUB_AUTOMATION_IDENTITY_TYPE": "restricted_bot",
            "ORCHESTRATOR_STATE_DIRECTORY": str(tmp_path / "state"),
        },
    )


def test_environment_removes_control_plane_secrets() -> None:
    cleaned = sanitized_agent_environment(
        {
            "PATH": "/usr/bin",
            "GITHUB_TOKEN": "secret-token",
            "OTHER_PASSWORD": "password",
            "GITHUB_PROJECT_NUMBER": "1",
        }
    )
    assert cleaned == {"PATH": "/usr/bin", "GITHUB_PROJECT_NUMBER": "1"}


def test_model_routing_escalates_after_repeated_failure(tmp_path: Path) -> None:
    config = configured(tmp_path)
    first = select_model(config, "product_manager", "create_feature_proposal", 1)
    third = select_model(config, "product_manager", "create_feature_proposal", 3)
    assert first.profile == "balanced"
    assert third.profile == "deep"


def test_state_store_reserves_side_effect_once(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state")
    store.create_workflow("wf-test", "FP-0001")
    assert store.reserve_effect("effect", "wf-test", "issue") is None
    assert store.reserve_effect("effect", "wf-test", "issue") is None
    store.complete_effect("effect", "7")
    assert store.reserve_effect("effect", "wf-test", "issue") == "7"


def test_proposal_workflow_publishes_once_and_waits_for_human(tmp_path: Path) -> None:
    config = configured(tmp_path)
    state = StateStore(config.runtime.state_directory)
    agent = FakeAgent()
    github = FakeGitHub()
    workflow = ProposalWorkflow(
        root=ROOT,
        config=config,
        state=state,
        agent=agent,
        github=github,
    )

    first = workflow.run()
    second = workflow.run()

    assert first["status"] == "waiting_human"
    assert second["workflow_id"] == first["workflow_id"]
    assert agent.calls == 2
    assert github.project_adds == 1
    assert len(github.comments) == 1
    assert github.field_values["Product Approval"] == "Pending"
    assert github.field_values["Current Role"] == "Human"
    assert "Implementation started: **no**" in github.comments[0][1]
