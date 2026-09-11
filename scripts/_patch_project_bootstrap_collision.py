from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"expected exactly one patch anchor in {path}: {old[:100]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_all(path: str, old: str, new: str, expected: int) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"expected {expected} patch anchors in {path}, found {count}")
    target.write_text(text.replace(old, new), encoding="utf-8")


replace_once(
    "scripts/orchestrator/github.py",
    '''def _same_instant(left: object, right: object) -> bool:\n    """Compare GitHub ISO-8601 timestamps by instant rather than raw formatting."""\n    if not isinstance(left, str) or not isinstance(right, str):\n        return False\n    try:\n        left_time = datetime.fromisoformat(left.replace("Z", "+00:00"))\n        right_time = datetime.fromisoformat(right.replace("Z", "+00:00"))\n    except ValueError:\n        return False\n    return left_time == right_time\n\n\n''',
    '''def _same_instant(left: object, right: object) -> bool:\n    """Compare GitHub ISO-8601 timestamps by instant rather than raw formatting."""\n    if not isinstance(left, str) or not isinstance(right, str):\n        return False\n    try:\n        left_time = datetime.fromisoformat(left.replace("Z", "+00:00"))\n        right_time = datetime.fromisoformat(right.replace("Z", "+00:00"))\n    except ValueError:\n        return False\n    return left_time == right_time\n\n\ndef _project_name_key(value: str) -> str:\n    """Normalize Project field/option names using GitHub's case-insensitive semantics."""\n    return value.strip().casefold()\n\n\ndef _field_by_name(fields: dict[str, "ProjectField"], name: str) -> "ProjectField" | None:\n    """Resolve a field without creating a casing/edge-whitespace duplicate."""\n    exact = fields.get(name)\n    if exact is not None:\n        return exact\n    key = _project_name_key(name)\n    matches = [\n        field\n        for existing_name, field in fields.items()\n        if _project_name_key(existing_name) == key\n    ]\n    if len(matches) > 1:\n        raise RuntimeError(f"GitHub Project has ambiguous fields matching {name!r}")\n    return matches[0] if matches else None\n\n\ndef _option_id_by_name(field: "ProjectField", name: str) -> str | None:\n    """Resolve a single-select option without duplicating a case variant."""\n    exact = field.options.get(name)\n    if exact is not None:\n        return exact\n    key = _project_name_key(name)\n    matches = [\n        option_id\n        for option_name, option_id in field.options.items()\n        if _project_name_key(option_name) == key\n    ]\n    if len(matches) > 1:\n        raise RuntimeError(f"GitHub Project field has ambiguous options matching {name!r}")\n    return matches[0] if matches else None\n\n\n''',
)

replace_all(
    "scripts/orchestrator/github.py",
    "field = project.fields.get(name)",
    "field = _field_by_name(project.fields, name)",
    3,
)
replace_once(
    "scripts/orchestrator/github.py",
    "missing = [item for item in options if item not in field.options]",
    "missing = [item for item in options if _option_id_by_name(field, item) is None]",
)
replace_once(
    "scripts/orchestrator/github.py",
    "missing = [option for option in contract_options if option not in field.options]",
    "missing = [option for option in contract_options if _option_id_by_name(field, option) is None]",
)
replace_once(
    "scripts/orchestrator/github.py",
    '''            existing = self._single_select_option_inputs(field.field_id)\n            by_name = {cast(str, option["name"]): option for option in existing}\n            merged: list[JsonObject] = []\n            for option_name in contract_options:\n                current = by_name.pop(option_name, None)\n''',
    '''            existing = self._single_select_option_inputs(field.field_id)\n            by_name = {\n                _project_name_key(cast(str, option["name"])): option for option in existing\n            }\n            merged: list[JsonObject] = []\n            for option_name in contract_options:\n                current = by_name.pop(_project_name_key(option_name), None)\n''',
)
replace_once(
    "scripts/orchestrator/github.py",
    "option_id = field.options.get(str(value))",
    "option_id = _option_id_by_name(field, str(value))",
)

with (ROOT / "tests/test_project_bootstrap.py").open("a", encoding="utf-8") as handle:
    handle.write(
        '''\n\ndef test_bootstrap_matches_existing_field_and_options_case_insensitively() -> None:\n    config = load_config(ROOT, environment={})\n    complete = _complete_snapshot(config)\n    fields = dict(complete.fields)\n    approval = fields.pop("Product Approval")\n    fields["product approval"] = approval\n    status_options = dict(complete.fields["Status"].options)\n    ready_id = status_options.pop("Ready")\n    status_options["ready"] = ready_id\n    fields["Status"] = ProjectField(\n        field_id=complete.fields["Status"].field_id,\n        data_type="SINGLE_SELECT",\n        options=status_options,\n    )\n    before = ProjectSnapshot(complete.project_id, complete.url, fields)\n    client = FakeProjectClient(config, before, complete)\n\n    result = client.reconcile_project_contract()\n\n    assert "Product Approval" not in result["created_fields"]\n    assert "Status" not in result["added_options"]\n    assert not any("createProjectV2Field" in query for query, _ in client.calls)\n\n\ndef test_project_verification_accepts_case_variant_names() -> None:\n    config = load_config(ROOT, environment={})\n    complete = _complete_snapshot(config)\n    fields = dict(complete.fields)\n    approval = fields.pop("Product Approval")\n    fields[" PRODUCT APPROVAL "] = approval\n    project = ProjectSnapshot(complete.project_id, complete.url, fields)\n    client = FakeProjectClient(config, project, project)\n\n    assert client.verify_project(project) == []\n'''
    )
