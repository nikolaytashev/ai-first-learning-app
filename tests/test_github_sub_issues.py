"""Regression tests for native GitHub sub-issue ordering."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.orchestrator.config import load_config
from scripts.orchestrator.github import GitHubClient
from scripts.orchestrator.model import IssueSnapshot, JsonObject

ROOT = Path(__file__).resolve().parents[1]


def _issue(database_id: int, number: int) -> IssueSnapshot:
    return IssueSnapshot(
        id=database_id,
        number=number,
        node_id=f"node-{number}",
        url=f"https://github.com/example/repo/issues/{number}",
        title=f"Issue {number}",
        body="",
        state="open",
        state_reason=None,
        author="bot",
        labels=(),
    )


class FakeSubIssueClient(GitHubClient):
    def __init__(self, siblings: list[IssueSnapshot]) -> None:
        self._config = load_config(ROOT, environment={})
        self._siblings = siblings
        self.calls: list[tuple[str, str, JsonObject | None]] = []

    def list_sub_issues(self, issue_number: int) -> list[IssueSnapshot]:
        assert issue_number == 21
        return self._siblings

    def _rest(self, method: str, path: str, payload: JsonObject | None = None) -> Any:
        self.calls.append((method, path, payload))
        return {}


def test_reprioritize_first_child_is_noop_when_already_first() -> None:
    child = _issue(101, 23)
    client = FakeSubIssueClient([child, _issue(102, 24)])

    client.reprioritize_sub_issue(21, child.id)

    assert client.calls == []


def test_reprioritize_only_child_is_noop() -> None:
    child = _issue(101, 23)
    client = FakeSubIssueClient([child])

    client.reprioritize_sub_issue(21, child.id)

    assert client.calls == []


def test_reprioritize_to_first_uses_before_id_not_null_after_id() -> None:
    first = _issue(101, 23)
    child = _issue(102, 24)
    client = FakeSubIssueClient([first, child])

    client.reprioritize_sub_issue(21, child.id)

    assert client.calls == [
        (
            "PATCH",
            "/repos/nikolaytashev/ai-first-learning-app/issues/21/sub_issues/priority",
            {"sub_issue_id": child.id, "before_id": first.id},
        )
    ]


def test_reprioritize_after_sibling_uses_after_id() -> None:
    first = _issue(101, 23)
    child = _issue(102, 24)
    client = FakeSubIssueClient([first, child])

    client.reprioritize_sub_issue(21, child.id, after_database_id=first.id)

    assert client.calls == [
        (
            "PATCH",
            "/repos/nikolaytashev/ai-first-learning-app/issues/21/sub_issues/priority",
            {"sub_issue_id": child.id, "after_id": first.id},
        )
    ]
