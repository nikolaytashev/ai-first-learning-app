from pathlib import Path


def patch_github() -> None:
    path = Path("scripts/orchestrator/github.py")
    text = path.read_text(encoding="utf-8")
    marker = "    def verify_branch_rules(self) -> list[str]:\n"
    insert = '''    def _single_select_option_inputs(self, field_id: str) -> list[JsonObject]:
        """Read option definitions so updates preserve existing option identities."""
        query = """
        query($id: ID!) {
          node(id: $id) {
            ... on ProjectV2SingleSelectField {
              options { id name color description }
            }
          }
        }
        """
        data = self._graphql(query, {"id": field_id})
        node = data.get("node")
        raw_options = node.get("options") if isinstance(node, dict) else None
        if not isinstance(raw_options, list):
            raise RuntimeError("GitHub Project single-select field omitted options")
        options: list[JsonObject] = []
        for raw in raw_options:
            if not isinstance(raw, dict):
                continue
            option_id = raw.get("id")
            name = raw.get("name")
            color = raw.get("color")
            description = raw.get("description")
            if all(isinstance(value, str) for value in (option_id, name, color, description)):
                options.append(
                    {
                        "id": cast(str, option_id),
                        "name": cast(str, name),
                        "color": cast(str, color),
                        "description": cast(str, description),
                    }
                )
        return options

    def reconcile_project_contract(self) -> JsonObject:
        """Create missing Project fields/options without deleting existing configuration."""
        project = self.project_snapshot()
        configured_url = self._config.project.url
        if configured_url and project.url.rstrip("/") != configured_url.rstrip("/"):
            raise RuntimeError("configured GitHub Project URL does not match project number")

        type_map = {
            "single_select": "SINGLE_SELECT",
            "number": "NUMBER",
            "text": "TEXT",
        }
        create_mutation = """
        mutation($input: CreateProjectV2FieldInput!) {
          createProjectV2Field(input: $input) { clientMutationId }
        }
        """
        update_mutation = """
        mutation($input: UpdateProjectV2FieldInput!) {
          updateProjectV2Field(input: $input) { clientMutationId }
        }
        """
        created_fields: list[str] = []
        added_options: dict[str, list[str]] = {}

        for name, raw_contract in self._config.project.required_fields.items():
            if not isinstance(raw_contract, dict):
                raise RuntimeError(f"invalid Project field contract for {name!r}")
            contract_type = raw_contract.get("type")
            if not isinstance(contract_type, str) or contract_type not in type_map:
                raise RuntimeError(f"unsupported Project field type for {name!r}")
            expected_type = type_map[contract_type]
            raw_options = raw_contract.get("options")
            contract_options: list[str] = []
            if raw_options is not None:
                if not isinstance(raw_options, list) or not all(
                    isinstance(item, str) and item for item in raw_options
                ):
                    raise RuntimeError(f"invalid Project options contract for {name!r}")
                contract_options = cast(list[str], raw_options)

            field = project.fields.get(name)
            if field is None:
                input_value: JsonObject = {
                    "projectId": project.project_id,
                    "dataType": expected_type,
                    "name": name,
                }
                if expected_type == "SINGLE_SELECT":
                    if not contract_options:
                        raise RuntimeError(
                            f"single-select Project field {name!r} requires at least one option"
                        )
                    input_value["singleSelectOptions"] = [
                        {"name": option, "color": "GRAY", "description": ""}
                        for option in contract_options
                    ]
                self._graphql(create_mutation, {"input": input_value})
                created_fields.append(name)
                continue

            if field.data_type != expected_type:
                raise RuntimeError(
                    f"Project field {name!r} has type {field.data_type}, expected {expected_type}; "
                    "bootstrap will not replace an existing field"
                )
            if expected_type != "SINGLE_SELECT" or not contract_options:
                continue

            missing = [option for option in contract_options if option not in field.options]
            if not missing:
                continue
            existing = self._single_select_option_inputs(field.field_id)
            by_name = {cast(str, option["name"]): option for option in existing}
            merged: list[JsonObject] = []
            for option_name in contract_options:
                current = by_name.pop(option_name, None)
                merged.append(
                    current
                    if current is not None
                    else {"name": option_name, "color": "GRAY", "description": ""}
                )
            merged.extend(by_name.values())
            self._graphql(
                update_mutation,
                {"input": {"fieldId": field.field_id, "singleSelectOptions": merged}},
            )
            added_options[name] = missing

        final_project = self.project_snapshot()
        errors = self.verify_project(final_project)
        if errors:
            raise RuntimeError("; ".join(errors))
        return {
            "status": "configured",
            "created_fields": created_fields,
            "added_options": added_options,
        }

'''
    if marker not in text:
        raise RuntimeError("github.py insertion marker not found")
    path.write_text(text.replace(marker, insert + marker, 1), encoding="utf-8")


def patch_cli() -> None:
    path = Path("scripts/run_orchestrator.py")
    text = path.read_text(encoding="utf-8")
    marker = "def usage() -> int:\n"
    insert = '''def project_bootstrap() -> int:
    """Reconcile GitHub Project fields/options to the checked-in contract."""
    try:
        config = load_config(ROOT)
        token_provider = load_github_token_provider(config, root=ROOT)
        github = GitHubClient(config, token_provider)
        errors = github.verify_identity_and_scope()
        if errors:
            raise RuntimeError("; ".join(errors))
        result = github.reconcile_project_contract()
    except (RuntimeError, ValueError) as exc:
        _print({"status": "failed", "error": str(exc)})
        return 1
    _print(result)
    return 0


'''
    if marker not in text:
        raise RuntimeError("CLI function marker not found")
    text = text.replace(marker, insert + marker, 1)
    old_choices = 'choices=("doctor", "usage", "policy", "resume", "iteration", "run", "proposal"),'
    new_choices = '''choices=(
            "doctor",
            "project-bootstrap",
            "usage",
            "policy",
            "resume",
            "iteration",
            "run",
            "proposal",
        ),'''
    if old_choices not in text:
        raise RuntimeError("CLI choices marker not found")
    text = text.replace(old_choices, new_choices, 1)
    dispatch_marker = '    if args.command == "usage":\n        return usage()\n'
    dispatch = '''    if args.command == "project-bootstrap":
        return project_bootstrap()
    if args.command == "usage":
        return usage()
'''
    if dispatch_marker not in text:
        raise RuntimeError("CLI dispatch marker not found")
    path.write_text(text.replace(dispatch_marker, dispatch, 1), encoding="utf-8")


def patch_readme() -> None:
    path = Path("README.md")
    text = path.read_text(encoding="utf-8")
    row = '| `python scripts/run_orchestrator.py doctor` | Fail-closed verification of local checkout, Codex, GitHub identity, Project fields and `main` ruleset. No agent execution or GitHub mutation. |\n'
    addition = row + '| `python -m scripts.run_orchestrator project-bootstrap` | Idempotently create missing Project custom fields and add missing single-select options from `config/github.yaml`. Existing fields/options are preserved; type mismatches fail closed. |\n'
    if row not in text:
        raise RuntimeError("README command marker not found")
    text = text.replace(row, addition, 1)
    old = '2. Ensure the Project contains all fields/options in `config/github.yaml`, including the new\n   `Origin` single-select field with `Human` and `Agent` options.\n'
    new = '2. Run `python -m scripts.run_orchestrator project-bootstrap` to reconcile the Project custom fields/options from `config/github.yaml`.\n'
    if old not in text:
        raise RuntimeError("README bootstrap marker not found")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def write_tests() -> None:
    Path("tests/test_project_bootstrap.py").write_text(
        '''"""Tests for idempotent GitHub Project schema bootstrap."""

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

    def _graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
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
        variables["input"]
        for query, variables in client.calls
        if "updateProjectV2Field" in query
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
''',
        encoding="utf-8",
    )


patch_github()
patch_cli()
patch_readme()
write_tests()
