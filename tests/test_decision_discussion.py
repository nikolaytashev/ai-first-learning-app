"""Regression coverage for dynamically routed Decision discussion."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts.orchestrator.commands import OrchestratorCommand
from scripts.orchestrator.decision_discussion import (
    has_pending_decision_command,
    process_decision_questions,
)
from scripts.orchestrator.model import IssueComment, IssueSnapshot, JsonObject


def _issue(number: int, title: str, body: str = "") -> IssueSnapshot:
    return IssueSnapshot(
        id=1000 + number,
        number=number,
        node_id=f"node-{number}",
        url=f"https://github.com/example/repo/issues/{number}",
        title=title,
        body=body,
        state="open",
        state_reason=None,
        author="nikolaytashev",
        labels=(),
    )


def _comment(comment_id: int, body: str, author: str = "nikolaytashev") -> IssueComment:
    return IssueComment(
        id=comment_id,
        url=f"https://github.com/example/repo/issues/26#issuecomment-{comment_id}",
        author=author,
        body=body,
        created_at="2026-09-16T04:00:00Z",
        updated_at="2026-09-16T04:00:00Z",
    )


class FakeGitHub:
    def __init__(self, comments: list[IssueComment]) -> None:
        self.issues = {
            21: _issue(21, "Parent Feature", "Canonical parent specification"),
            26: _issue(26, "[Decision]: Delivery", "Managed Decision specification"),
        }
        self.comments = list(comments)
        self.added: list[str] = []

    def get_issue(self, issue_number: int) -> IssueSnapshot:
        return self.issues[issue_number]

    def list_comments(self, issue_number: int) -> list[IssueComment]:
        del issue_number
        return list(self.comments)

    def find_comment_by_marker(self, issue_number: int, marker: str) -> IssueComment | None:
        del issue_number
        for comment in self.comments:
            if marker in comment.body:
                return comment
        for index, body in enumerate(self.added, start=10000):
            if marker in body:
                return _comment(index, body, author="automation")
        return None

    def add_comment(self, issue_number: int, body: str) -> None:
        assert issue_number == 26
        self.added.append(body)


class FakeRoleRunner:
    def __init__(
        self,
        *,
        question_comment_id: int,
        primary: str,
        consult: list[str] | None = None,
    ) -> None:
        self.question_comment_id = question_comment_id
        self.primary = primary
        self.consult = consult or []
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> JsonObject:
        self.calls.append(dict(kwargs))
        if kwargs["schema"] == "decision-question-routing.schema.json":
            return {
                "schema_version": 1,
                "question_comment_id": self.question_comment_id,
                "primary_role": self.primary,
                "consult_roles": self.consult,
                "question_type": "cross_functional" if self.consult else "requirements",
                "confidence": "high",
                "rationale": "The question matches the selected role boundary.",
            }
        role = str(kwargs["role"])
        return {
            "schema_version": 1,
            "question_comment_id": self.question_comment_id,
            "role": role,
            "answer": f"Answer from {role}",
            "caveats": [],
        }


def _command(comment_id: int, argument: str = "") -> OrchestratorCommand:
    return OrchestratorCommand(
        name="ask",
        argument=argument,
        comment_id=comment_id,
        actor="nikolaytashev",
    )


def test_idle_decision_does_not_consume_reconciliation_slot_until_command_arrives() -> None:
    question = _comment(10, "Can you explain the trade-offs?")
    assert not has_pending_decision_command(
        [question],
        command_prefix="/orch",
        accepted_commands=("ask",),
    )

    ask = _comment(11, "/orch ask")
    assert has_pending_decision_command(
        [question, ask],
        command_prefix="/orch",
        accepted_commands=("ask",),
    )


def test_same_comment_question_routes_to_business_analysis() -> None:
    comment = _comment(10, "What business rule controls this?\n\n/orch ask")
    github = FakeGitHub([comment])
    runner = FakeRoleRunner(question_comment_id=10, primary="business_analysis")

    answered = process_decision_questions(
        root=Path.cwd(),
        application_root=Path.cwd(),
        github=github,  # type: ignore[arg-type]
        issue=github.get_issue(26),
        metadata={"parent": 21},
        new_comments=[comment],
        commands=[_command(10)],
        human_approvers=("nikolaytashev",),
        command_prefix="/orch",
        run_role=runner,
    )

    assert answered == 1
    assert [call["role"] for call in runner.calls] == [
        "product_manager",
        "business_analysis",
    ]
    assert "Routed to **Business Analysis**" in github.added[0]
    assert "Answer from business_analysis" in github.added[0]
    assert "does not resolve this Decision" in github.added[0]


def test_command_only_ask_uses_previous_question_and_can_consult_specialist() -> None:
    question = _comment(10, "How will the data be stored and delivered to the client?")
    ask = _comment(11, "/orch ask")
    github = FakeGitHub([question, ask])
    runner = FakeRoleRunner(
        question_comment_id=11,
        primary="software_architect",
        consult=["business_analysis"],
    )

    answered = process_decision_questions(
        root=Path.cwd(),
        application_root=Path.cwd(),
        github=github,  # type: ignore[arg-type]
        issue=github.get_issue(26),
        metadata={"parent": 21},
        new_comments=[question, ask],
        commands=[_command(11)],
        human_approvers=("nikolaytashev",),
        command_prefix="/orch",
        run_role=runner,
    )

    assert answered == 1
    assert [call["role"] for call in runner.calls] == [
        "product_manager",
        "business_analysis",
        "software_architect",
    ]
    assert "Routed to **Software Architect**; consulted **Business Analysis**" in github.added[0]
    assert "How will the data be stored" in runner.calls[0]["prompt"]


def test_existing_answer_marker_makes_retry_idempotent() -> None:
    question = _comment(10, "Question\n/orch ask")
    existing_answer = _comment(20, "<!-- orch-answer:10 -->\nAlready answered", author="automation")
    github = FakeGitHub([question, existing_answer])
    runner = FakeRoleRunner(question_comment_id=10, primary="product_manager")

    answered = process_decision_questions(
        root=Path.cwd(),
        application_root=Path.cwd(),
        github=github,  # type: ignore[arg-type]
        issue=github.get_issue(26),
        metadata={"parent": 21},
        new_comments=[question],
        commands=[_command(10)],
        human_approvers=("nikolaytashev",),
        command_prefix="/orch",
        run_role=runner,
    )

    assert answered == 0
    assert runner.calls == []
    assert github.added == []


def test_ask_without_question_text_is_rejected() -> None:
    ask = _comment(11, "/orch ask")
    github = FakeGitHub([ask])
    runner = FakeRoleRunner(question_comment_id=11, primary="product_manager")

    with pytest.raises(ValueError, match="requires question text"):
        process_decision_questions(
            root=Path.cwd(),
            application_root=Path.cwd(),
            github=github,  # type: ignore[arg-type]
            issue=github.get_issue(26),
            metadata={"parent": 21},
            new_comments=[ask],
            commands=[_command(11)],
            human_approvers=("nikolaytashev",),
            command_prefix="/orch",
            run_role=runner,
        )
