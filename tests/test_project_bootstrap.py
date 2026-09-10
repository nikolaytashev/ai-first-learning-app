"""Tests for idempotent GitHub Project schema bootstrap."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts.orchestrator.config import load_config
from scripts.orchestrator.github import GitHubClient, ProjectField, ProjectSnapshot

ROOT = Path(__file__).resolve().parents[1]


def _field(data_type: str, options: list[str] | None = None) -> ProjectField:
    return ProjectField(
        field_id=f"field-{data_type}-{len(options or [])}",
        data_type=data_type,
        options={name: f"option-{name}" for name in options or []},
    )


def _complete_snapshot(config: Any) -> ProjectSnapshot:
    type_map = {"single_select": "SINGLE_SELECT", "number": "NUMBER", "text": "TEXT"}
    fields: dict[str, ProjectField] = {}
    for name, contract in config.project.required_fields.items():
        fields[name] = _field(type_map[contract["type"]], contract.get("options"))
    return ProjectSnapshot(
        project_id="project-1",
        url="https://github.com/users/nikolaytashev/projects/1",
        fields=fields,
    )


class FakeProjectClient(GitHubClient):
    def __init__(self, config: Any, before: ProjectSnapshot, after: ProjectSnapshot) -> None:
        self._config = config
        self._snapshots = [before, after]
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def project_snapshot(self) -> ProjectSnapshot:
        return self._snapshots.pop(0) if len(self._snapshots) > 1 else self._snapshots[0]

    def _project_graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((query, variables))
        return {}

    def _single_select_option_inputs(self, field_id: str) -> list[dict[str, Any]]:
        assert field_id
        return [
            {
                "id": "option-ready",
                "name": "Ready",
                "color": "GREEN",
                "description": "existing",
            }
        ]


def test_bootstrap_creates_fields_and_preserves_existing_options() -> None:
    config = load_config(ROOT, environment={})
    after = _complete_snapshot(config)
    before_fields = dict(after.fields)
    before_fields.pop("Product Approval")
    before_fields["Status"] = _field("SINGLE_SELECT", ["Ready"])
    before = ProjectSnapshot(after.project_id, after.url, before_fields)
    client = FakeProjectClient(config, before, after)

    result = client.reconcile_project_contract()

    assert result["status"] == "configured"
    assert "Product Approval" in result["created_fields"]
    assert result["added_options"]["Status"] == [
        "Inbox",
        "In Progress",
        "In Review",
        "Awaiting Human",
        "Blocked",
        "Done",
        "Cancelled",
    ]
    updates = [
        variables["input"] for query, variables in client.calls if "updateProjectV2Field" in query
    ]
    status_update = next(item for item in updates if "singleSelectOptions" in item)
    ready = next(
        option for option in status_update["singleSelectOptions"] if option["name"] == "Ready"
    )
    assert ready["id"] == "option-ready"
    assert ready["color"] == "GREEN"


def test_bootstrap_refuses_existing_type_mismatch() -> None:
    config = load_config(ROOT, environment={})
    complete = _complete_snapshot(config)
    fields = dict(complete.fields)
    fields["Attempt Count"] = _field("TEXT")
    before = ProjectSnapshot(complete.project_id, complete.url, fields)
    client = FakeProjectClient(config, before, complete)

    with pytest.raises(RuntimeError, match="bootstrap will not replace"):
        client.reconcile_project_contract()
