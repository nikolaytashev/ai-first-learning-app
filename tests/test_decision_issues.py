"""Regression coverage for first-class human Decision issues."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast

import pytest

from scripts.orchestrator.commands import OrchestratorCommand
from scripts.orchestrator.control_plane import (
    ControlPlaneWorkflow,
    _decision_key,
    parse_metadata,
)
from scripts.orchestrator.model import IssueComment, IssueRef, IssueSnapshot, JsonObject


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
        self._config = cast(
            Any,
            SimpleNamespace(authorization=SimpleNamespace(command_prefix="/orch")),
        )
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
        {
            "decisions_required": [{"key": "decision-content", "statement": text}],
            "priority": "P2",
            "revision": 4,
        },
    )

    assert github.created == 0
    assert resolved[0][1].number == 26
    updated = github.get_issue(26)
    updated_meta = parse_metadata(updated.body)
    assert updated_meta is not None
    assert updated_meta["key"] == "decision-content"
    assert updated_meta["decision_text"] == text
    assert cast(list[str], updated_meta["decision_aliases"]) == []
    assert updated_meta["origin"] == "Human"
    assert updated.title == "[Decision]: Content delivery"
    assert "Human architecture analysis." in updated.body


def test_decision_approval_does_not_reuse_question_text_across_ask_command() -> None:
    parent_body = (
        '<!-- orch-meta:{"approval":"pending","managed":true,"origin":"Agent",'
        '"parent":null,"schema":1,"type":"Feature"} -->\n'
    )
    decision_body = (
        '<!-- orch-meta:{"decision_text":"Choose delivery","execution_state":"waiting_human",'
        '"key":"decision-delivery","managed":true,"origin":"Human","parent":21,'
        '"schema":1,"type":"Decision"} -->\n'
    )
    parent = _issue(21, title="Feature", body=parent_body)
    decision = _issue(26, title="[Decision]: Delivery", body=decision_body, author="human")
    github = FakeDecisionGitHub([parent, decision])
    workflow = DecisionWorkflow(github)
    comments = [
        IssueComment(
            id=70,
            url="https://github.com/example/repo/issues/26#issuecomment-70",
            author="nikolaytashev",
            body="Can you explain option B in more detail?",
            created_at="2026-09-20T00:00:00Z",
            updated_at="2026-09-20T00:00:00Z",
        ),
        IssueComment(
            id=71,
            url="https://github.com/example/repo/issues/26#issuecomment-71",
            author="nikolaytashev",
            body="/orch ask",
            created_at="2026-09-20T00:01:00Z",
            updated_at="2026-09-20T00:01:00Z",
        ),
        IssueComment(
            id=72,
            url="https://github.com/example/repo/issues/26#issuecomment-72",
            author="nikolaytashev",
            body="/orch approve",
            created_at="2026-09-20T00:02:00Z",
            updated_at="2026-09-20T00:02:00Z",
        ),
    ]
    command = OrchestratorCommand(
        name="approve",
        argument="",
        comment_id=72,
        actor="nikolaytashev",
    )

    with pytest.raises(ValueError, match="requires the chosen decision text"):
        workflow._resolve_decision(
            decision,
            cast(JsonObject, parse_metadata(decision.body)),
            comments,
            command,
        )


def test_duplicate_explicit_decision_keys_fail_closed() -> None:
    parent = _issue(21, title="Feature", body="")
    github = FakeDecisionGitHub([parent])
    workflow = DecisionWorkflow(github)

    with pytest.raises(RuntimeError, match="duplicate decision gate key"):
        workflow._active_decisions(
            21,
            {
                "decisions_required": [
                    {"key": "decision-retention", "statement": "Retain data for 30 days."},
                    {"key": "decision-retention", "statement": "Retain data for 90 days."},
                ]
            },
        )


def test_post_approval_rewording_uses_stable_decision_identity() -> None:
    stable_key = "decision-content-delivery"
    original = "Choose the approved content delivery pipeline and publication boundary."
    reworded = "Select the publication boundary and delivery path for approved lesson content."
    parent_body = (
        '<!-- orch-meta:{"decision_resolutions":[{"decision_issue_number":26,'
        '"decision_key":"' + stable_key + '","decision_text":"' + original + '",'
        '"resolution":"Option B"}],"managed":true,"origin":"Agent","parent":null,'
        '"schema":1,"type":"Feature"} -->\n'
    )
    parent = _issue(21, title="Feature", body=parent_body)
    github = FakeDecisionGitHub([parent])
    workflow = DecisionWorkflow(github)

    active = workflow._active_decisions(
        21,
        {
            "decisions_required": [{"key": stable_key, "statement": reworded}],
            "priority": "P2",
            "revision": 6,
        },
    )

    assert active == []


def test_materially_changed_gate_requires_new_stable_identity() -> None:
    resolved_key = "decision-retention-period"
    new_key = "decision-retention-period-90-days"
    parent_body = (
        '<!-- orch-meta:{"decision_resolutions":[{"decision_issue_number":26,'
        '"decision_key":"' + resolved_key + '","decision_text":"Retain customer data for 30 days.",'
        '"resolution":"30 days"}],"managed":true,"origin":"Agent","parent":null,'
        '"schema":1,"type":"Feature"} -->\n'
    )
    parent = _issue(21, title="Feature", body=parent_body)
    github = FakeDecisionGitHub([parent])
    workflow = DecisionWorkflow(github)

    active = workflow._active_decisions(
        21,
        {
            "decisions_required": [
                {"key": new_key, "statement": "Retain customer data for 90 days."}
            ],
            "priority": "P2",
            "revision": 7,
        },
    )

    assert active == [{"key": new_key, "statement": "Retain customer data for 90 days."}]


def test_resolved_decision_suppresses_only_explicitly_recorded_aliases() -> None:
    original = "Choose the approved content delivery pipeline and publication boundary."
    reworded = "Choose the approved-content delivery pipeline and publication boundary."
    distinct = "Choose the account deletion retention policy."
    stable_key = "decision-content-delivery"
    parent = _issue(21, title="Feature", body="")
    decision_body = (
        '<!-- orch-meta:{"approval":"approved","decision_aliases":["'
        + _decision_key(reworded)
        + '"],"decision_text":"'
        + original
        + '","key":"'
        + stable_key
        + '","managed":true,"origin":"Human","parent":21,'
        '"resolution":{"comment_id":77},"schema":1,"type":"Decision"} -->\n'
    )
    decision = _issue(26, title="[Decision]: Delivery", body=decision_body, author="human")
    github = FakeDecisionGitHub([parent, decision])
    workflow = DecisionWorkflow(github)

    active = workflow._active_decisions(
        21,
        {
            "decisions_required": [reworded, distinct],
            "priority": "P2",
            "revision": 5,
        },
    )

    assert active == [{"key": _decision_key(distinct), "statement": distinct}]


def test_similar_decision_with_changed_critical_value_remains_active() -> None:
    resolved = "Retain customer data for 30 days."
    changed = "Retain customer data for 90 days."
    parent = _issue(21, title="Feature", body="")
    decision_body = (
        '<!-- orch-meta:{"approval":"approved","decision_aliases":[],"decision_text":"'
        + resolved
        + '","key":"'
        + _decision_key(resolved)
        + '","managed":true,"origin":"Human","parent":21,'
        '"resolution":{"comment_id":77},"schema":1,"type":"Decision"} -->\n'
    )
    decision = _issue(26, title="[Decision]: Retention", body=decision_body, author="human")
    github = FakeDecisionGitHub([parent, decision])
    workflow = DecisionWorkflow(github)

    active = workflow._active_decisions(
        21,
        {"decisions_required": [changed], "priority": "P2", "revision": 6},
    )

    assert active == [{"key": _decision_key(changed), "statement": changed}]


def test_resolved_decision_is_suppressed_before_analysis_state_is_persisted() -> None:
    text = "Choose the canonical lesson delivery contract."
    parent = _issue(21, title="Feature", body="")
    decision_body = (
        '<!-- orch-meta:{"approval":"approved","key":"'
        + _decision_key(text)
        + '","managed":true,"origin":"Human","parent":21,"resolution":{"comment_id":77},'
        '"schema":1,"type":"Decision"} -->\n'
    )
    decision = _issue(26, title="[Decision]: Delivery", body=decision_body, author="human")
    github = FakeDecisionGitHub([parent, decision])
    workflow = DecisionWorkflow(github)
    analysis: JsonObject = {
        "decisions_required": [text, "Choose a distinct unresolved policy."],
        "priority": "P2",
        "revision": 5,
    }

    active = workflow._active_decisions(21, analysis)

    assert active == [
        {
            "key": _decision_key("Choose a distinct unresolved policy."),
            "statement": "Choose a distinct unresolved policy.",
        }
    ]


def test_closed_resolved_decision_is_suppressed_from_parent_history() -> None:
    text = "Choose the canonical lesson delivery contract."
    key = _decision_key(text)
    parent_body = (
        '<!-- orch-meta:{"decision_resolutions":[{"decision_issue_number":26,'
        '"decision_key":"' + key + '","resolution":"Option B"}],"managed":true,'
        '"origin":"Agent","parent":null,"schema":1,"type":"Feature"} -->\n'
    )
    parent = _issue(21, title="Feature", body=parent_body)
    closed_decision = _issue(
        26,
        title="[Decision]: Delivery",
        body='<!-- orch-meta:{"managed":true,"origin":"Human","parent":21,'
        '"schema":1,"type":"Decision"} -->\n',
        author="human",
        state="closed",
        state_reason="completed",
    )
    github = FakeDecisionGitHub([parent, closed_decision])
    workflow = DecisionWorkflow(github)

    active = workflow._active_decisions(
        21,
        {"decisions_required": [text], "priority": "P2", "revision": 6},
    )

    assert active == []


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


def test_clearing_pending_decisions_preserves_latest_reconciliation_metadata() -> None:
    parent_body = (
        '<!-- orch-meta:{"agent_replan_requests":[],"approval":"pending",'
        '"managed":true,"origin":"Agent","parent":null,'
        '"pending_decision_resolutions":[{"comment_id":77}],'
        '"schema":1,"type":"Feature"} -->\n'
    )
    parent = _issue(21, title="Feature", body=parent_body)
    github = FakeDecisionGitHub([parent])
    workflow = DecisionWorkflow(github)

    _, metadata = workflow._clear_pending_decision_resolutions(21)

    assert metadata["pending_decision_resolutions"] == []
    assert metadata["agent_replan_requests"] == []


def test_decision_approval_records_resolution_and_queues_parent_replan() -> None:
    parent_body = (
        '<!-- orch-meta:{"approval":"pending","managed":true,"origin":"Agent",'
        '"parent":null,"schema":1,"type":"Feature"} -->\n'
    )
    decision_body = (
        '<!-- orch-meta:{"decision_text":"Choose delivery","execution_state":"waiting_human",'
        '"key":"decision-delivery","managed":true,"origin":"Human","parent":21,'
        '"schema":1,"type":"Decision"} -->\n'
    )
    parent = _issue(21, title="Feature", body=parent_body)
    decision = _issue(26, title="[Decision]: Delivery", body=decision_body, author="human")
    github = FakeDecisionGitHub([parent, decision])
    workflow = DecisionWorkflow(github)
    comment = IssueComment(
        id=77,
        url="https://github.com/example/repo/issues/26#issuecomment-77",
        author="nikolaytashev",
        body="I choose option B.\n\n/orch approve",
        created_at="2026-09-20T00:00:00Z",
        updated_at="2026-09-20T00:00:00Z",
    )
    command = OrchestratorCommand(
        name="approve",
        argument="",
        comment_id=77,
        actor="nikolaytashev",
    )

    _, metadata = workflow._resolve_decision(
        decision,
        cast(JsonObject, parse_metadata(decision.body)),
        [comment],
        command,
    )

    resolution = cast(dict[str, Any], metadata["resolution"])
    assert resolution["resolution"] == "I choose option B."
    assert metadata["approval"] == "approved"
    assert metadata["execution_state"] == "resolved_pending_replan"

    parent_meta = parse_metadata(github.get_issue(21).body)
    assert parent_meta is not None
    pending = cast(list[dict[str, Any]], parent_meta["pending_decision_resolutions"])
    assert pending[0]["decision_issue_number"] == 26
    assert pending[0]["comment_id"] == 77
    assert pending[0]["resolution"] == "I choose option B."
    history = cast(list[dict[str, Any]], parent_meta["decision_resolutions"])
    assert len(history) == 1

    workflow._resolve_decision(
        github.get_issue(26),
        metadata,
        [comment],
        command,
    )
    retry_parent_meta = parse_metadata(github.get_issue(21).body)
    assert retry_parent_meta is not None
    assert len(cast(list[Any], retry_parent_meta["pending_decision_resolutions"])) == 1
    assert len(cast(list[Any], retry_parent_meta["decision_resolutions"])) == 1

    correction = IssueComment(
        id=78,
        url="https://github.com/example/repo/issues/26#issuecomment-78",
        author="nikolaytashev",
        body="Correction: I choose option C.\n\n/orch approve",
        created_at="2026-09-20T00:01:00Z",
        updated_at="2026-09-20T00:01:00Z",
    )
    correction_command = OrchestratorCommand(
        name="approve",
        argument="",
        comment_id=78,
        actor="nikolaytashev",
    )
    workflow._resolve_decision(
        github.get_issue(26),
        metadata,
        [comment, correction],
        correction_command,
    )
    corrected_parent_meta = parse_metadata(github.get_issue(21).body)
    assert corrected_parent_meta is not None
    corrected_pending = cast(
        list[dict[str, Any]], corrected_parent_meta["pending_decision_resolutions"]
    )
    corrected_history = cast(list[dict[str, Any]], corrected_parent_meta["decision_resolutions"])
    assert len(corrected_pending) == 1
    assert corrected_pending[0]["comment_id"] == 78
    assert corrected_pending[0]["resolution"] == "Correction: I choose option C."
    assert len(corrected_history) == 1
    assert corrected_history[0]["comment_id"] == 78

    assert workflow.status_updates[-2]["number"] == 26
    assert workflow.status_updates[-2]["status"] == "In Review"
    assert workflow.status_updates[-1]["number"] == 21
    assert workflow.status_updates[-1]["automation"] == "Queued"
