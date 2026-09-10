from pathlib import Path

path = Path("scripts/orchestrator/implementation.py")
text = path.read_text(encoding="utf-8")
replacements = [
    (
        '        branch = self._branch_name(task, metadata)\n',
        '        branch = self._branch_name(task, metadata, workflow_id)\n',
    ),
    (
        '    def _branch_name(task: IssueSnapshot, metadata: JsonObject) -> str:\n',
        '    def _branch_name(\n        task: IssueSnapshot, metadata: JsonObject, workflow_id: str\n    ) -> str:\n',
    ),
    (
        '        return f"agent/task-{task.number}-{slug}"\n',
        '        attempt = re.sub(r"[^a-z0-9]+", "-", workflow_id.lower()).strip("-")[-12:]\n        return f"agent/task-{task.number}-{slug}-{attempt}"\n',
    ),
]
for old, new in replacements:
    if old not in text:
        raise SystemExit(f"implementation anchor not found: {old!r}")
    text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")

test_path = Path("tests/test_runtime_completion_contracts.py")
test = test_path.read_text(encoding="utf-8")
anchor = '    assert \'"rebase"\' in implementation\n'
replacement = anchor + '    assert "workflow_id: str" in implementation\n    assert "agent/task-{task.number}-{slug}-{attempt}" in implementation\n'
if anchor not in test:
    raise SystemExit("test anchor not found")
test_path.write_text(test.replace(anchor, replacement, 1), encoding="utf-8")
