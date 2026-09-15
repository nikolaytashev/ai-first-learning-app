"""Regression coverage for first-class human Decision issues."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

from scripts.orchestrator.control_plane import (
    ControlPlaneWorkflow,
    _decision_key,
    parse_metadata,
)
from scripts.orchestrator.model import IssueRef, IssueSnapshot, JsonObject


def _issue(
    number: int,
    *,
    title: str,
    body: str,
    author: str = "automation",
    state: str = "open",
    state_reason: str | None = None,
) -> IssueSnapshot:
    return IssueSnapshot(
        id=1000 + number,
        number=number,
        node_id=f"node-{number}",
        url=f"https://github.com/example/repo/issues/{number}",
        title=title,
        body=body,
        state=state,
        state_reason=state_reason,
        author=author,
        labels=(),
    )


class FakeDecisionGitHub:
    def __init__(self, issues: list[IssueSnapshot]) -> None:
        self.issues = {issue.number: issue for issue in issues}
        self.created = 0

    def list_issues(self, *, state: str = "open") -> list[IssueSnapshot]:
        return [issue for issue in self.issues.values() if state == "all" or issue.state == state]

    def create_issue(self, title: str, body: str) -> IssueRef:
        self.created += 1
        number = max(self.issues, default=0) + 1
        issue = _issue(number, title=title, body=body)
        self.issues[number] = issue
        return issue.ref

    def get_issue(self, issue_number: int) -> IssueSnapshot:
        return self.issues[issue_number]

    def update_issue(self, issue_number: int, **changes: Any) -> IssueSnapshot:
        issue = self.issues[issue_number]
        allowed = {
            key: value
            for key, value in changes.items()
            if key in {"title", "body", "state", "state_reason"} and value is not None
        }
        updated = replace(issue, **allowed)
        self.issues[issue_number] = updated
        return updated


class DecisionWorkflow(ControlPlaneWorkflow):
    def __init__(self, github: FakeDecisionGitHub) -> None:
        self._github = cast(Any, github)
        self._project = None
        self.project_updates: list[JsonObject] = []
        self.status_updates: list[JsonObject] = []
        self.audits: list[str] = []

    def _ensure_project_fields(
        self,
        issue: IssueSnapshot,
        *,
        artifact_type: str,
        origin: str,
        status: str,
        approval: str,
        priority: str,
        size: str,
        role: str,
        automation: str,
    ) -> None:
        self.project_updates.append(
            {
                "number": issue.number,
                "artifact_type": artifact_type,
                "origin": origin,
                "status": status,
                "approval": approval,
                "priority": priority,
                "size": size,
                "role": role,
                "automation": automation,
            }
        )

    def _set_project_status(
        self,
        issue: IssueSnapshot,
        status: str,
        approval: str,
        role: str,
        automation: str,
    ) -> None:
        self.status_updates.append(
            {
                "number": issue.number,
                "status": status,
                "approval": approval,
                "role": role,
                "automation": automation,
            }
        )

    def _audit(self, issue_number: int, message: str, *, marker: str | None = None) -> None:
        self.audits.append(f"{issue_number}:{message}:{marker or ''}")


def test_decision_requirement_materializes_once_and_is_linked_to_parent() -> None:
    parent = _issue(21, title="Feature", body="")
    github = FakeDecisionGitHub([parent])
    workflow = DecisionWorkflow(github)
    metadata: JsonObject = {"revision": 3}
    analysis: JsonObject = {
        "decisions_required": ["Choose the canonical lesson delivery contract."],
        "priority": "P2",
        "revision": 3,
    }

    first = workflow._sync_decision_issues(parent, metadata, analysis)
    second = workflow._sync_decision_issues(parent, metadata, analysis)

    assert github.created == 1
    assert first[0][1].number == second[0][1].number
    decision = github.get_issue(first[0][1].number)
    decision_meta = parse_metadata(decision.body)
    assert decision_meta is not None
    assert decision_meta["type"] == "Decision"
    assert decision_meta["parent"] == 21
    assert decision_meta["key"] == _decision_key("Choose the canonical lesson delivery contract.")
    assert metadata["decision_issue_numbers"] == [decision.number]
    assert workflow.project_updates[-1]["artifact_type"] == "Decision"
    assert workflow.project_updates[-1]["status"] == "Awaiting Human"


def test_single_human_decision_is_reused_when_reanalysis_rewords_the_gate() -> None:
    parent = _issue(21, title="Feature", body="")
    human_body = (
        '<!-- orch-meta:{"key":"decision-content","managed":true,"origin":"Human",'
        '"parent":21,"schema":1,"type":"Decision"} -->\n\nHuman architecture analysis.'
    )
    decision = _issue(26, title="[Decision]: Content delivery", body=human_body, author="human")
    github = FakeDecisionGitHub([parent, decision])
    workflow = DecisionWorkflow(github)
    metadata: JsonObject = {"revision": 4}
    text = "Choose the approved-content delivery pipeline and publication boundary."

    resolved = workflow._sync_decision_issues(
        parent,
        metadata,
        {"decisions_required": [text], "priority": "P2", "revision": 4},
    )

    assert github.created == 0
    assert resolved[0][1].number == 26
    updated = github.get_issue(26)
    updated_meta = parse_metadata(updated.body)
    assert updated_meta is not None
    assert updated_meta["key"] == _decision_key(text)
    assert updated_meta["origin"] == "Human"
    assert updated.title == "[Decision]: Content delivery"
    assert "Human architecture analysis." in updated.body


def test_decision_issue_closes_when_parent_no_longer_requires_it() -> None:
    parent = _issue(21, title="Feature", body="")
    decision_body = (
        '<!-- orch-meta:{"key":"decision-old","managed":true,"origin":"Agent",'
        '"parent":21,"schema":1,"type":"Decision"} -->\n'
    )
    decision = _issue(26, title="[Decision]: Old gate", body=decision_body)
    github = FakeDecisionGitHub([parent, decision])
    workflow = DecisionWorkflow(github)
    metadata: JsonObject = {"revision": 5}

    resolved = workflow._sync_decision_issues(
        parent,
        metadata,
        {"decisions_required": [], "priority": "P2", "revision": 5},
    )

    assert resolved == []
    closed = github.get_issue(26)
    assert closed.state == "closed"
    assert closed.state_reason == "completed"
    closed_meta = parse_metadata(closed.body)
    assert closed_meta is not None
    assert closed_meta["execution_state"] == "completed"
    assert metadata["decision_issue_numbers"] == []
    assert workflow.status_updates[-1]["status"] == "Done"
