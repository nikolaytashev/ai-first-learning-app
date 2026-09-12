"""Tests for Codex structured-output compatibility and diagnostics."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

from scripts.orchestrator.codex import (
    CodexCliRunner,
    CodexInvocationError,
    _codex_failure_detail,
    codex_output_schema,
)
from scripts.orchestrator.model import JsonObject, ModelSelection
from scripts.validate_repository import ROOT

_FORBIDDEN_CODEX_KEYS = {
    "$schema",
    "$id",
    "title",
    "const",
    "oneOf",
    "allOf",
    "not",
    "if",
    "then",
    "else",
    "dependentRequired",
    "dependentSchemas",
    "uniqueItems",
    "minLength",
    "maxLength",
    "pattern",
    "format",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minItems",
    "maxItems",
}


def _load(path: Path) -> JsonObject:
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return cast(JsonObject, raw)


def _assert_codex_subset(value: Any) -> None:
    if not isinstance(value, dict):
        return
    assert not (_FORBIDDEN_CODEX_KEYS & set(value))

    properties = value.get("properties")
    schema_type = value.get("type")
    is_object = schema_type == "object" or (
        isinstance(schema_type, list) and "object" in schema_type
    )
    if is_object or isinstance(properties, dict):
        assert value.get("additionalProperties") is False
        if isinstance(properties, dict):
            assert set(value.get("required", [])) == set(properties)
            for child in properties.values():
                _assert_codex_subset(child)

    definitions = value.get("$defs")
    if isinstance(definitions, dict):
        for child in definitions.values():
            _assert_codex_subset(child)

    items = value.get("items")
    if items is not None:
        _assert_codex_subset(items)

    variants = value.get("anyOf")
    if isinstance(variants, list):
        for child in variants:
            _assert_codex_subset(child)


def test_all_agent_schemas_project_to_conservative_codex_subset() -> None:
    schema_paths = sorted((ROOT / "schemas").glob("*.schema.json"))
    assert schema_paths
    for schema_path in schema_paths:
        projected = codex_output_schema(_load(schema_path))
        _assert_codex_subset(projected)


def test_projection_converts_const_and_preserves_full_schema_on_disk() -> None:
    schema_path = ROOT / "schemas" / "feature-proposal.schema.json"
    original = _load(schema_path)
    projected = codex_output_schema(original)

    properties = projected["properties"]
    assert isinstance(properties, dict)
    assert properties["schema_version"] == {"enum": [1]}
    assert "allOf" in original
    assert "allOf" not in projected


def test_failed_codex_jsonl_diagnostics_include_stdout_and_redact_secrets() -> None:
    stdout = (
        '{"type":"item.completed","item":'
        '{"type":"error","message":"Invalid output schema token-secret"}}\n'
        '{"type":"turn.failed","error":{"message":"request rejected"}}\n'
    )
    detail = _codex_failure_detail(
        stdout,
        "backend failed",
        {"GITHUB_TOKEN": "token-secret"},
    )

    assert "Invalid output schema [REDACTED]" in detail
    assert "request rejected" in detail
    assert "backend failed" in detail
    assert "token-secret" not in detail


def test_nonzero_codex_exit_preserves_completed_turn_usage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
                "additionalProperties": False,
            }
        ),
        encoding="utf-8",
    )
    stdout = (
        '{"type":"thread.started","thread_id":"thread-1"}\n'
        '{"type":"turn.completed","usage":{"input_tokens":12,"output_tokens":3}}\n'
        '{"type":"error","message":"provider rejected result"}\n'
    )

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 1, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner = CodexCliRunner(root=tmp_path, environment={})
    model = ModelSelection("balanced", "openai", "gpt-test", "medium")

    with pytest.raises(CodexInvocationError) as captured:
        runner.run(
            prompt="test",
            schema_path=schema_path,
            model=model,
            timeout_seconds=30,
        )

    assert captured.value.usage is not None
    assert captured.value.usage.input_tokens == 12
    assert captured.value.usage.output_tokens == 3
    assert captured.value.thread_id == "thread-1"
