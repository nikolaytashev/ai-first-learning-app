"""Codex CLI execution adapter with structured-output and telemetry checks."""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from scripts.orchestrator.model import CodexRun, JsonObject, ModelSelection, Usage

_SECRET_NAMES = {
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "GITHUB_APP_PRIVATE_KEY",
    "GITHUB_APP_PRIVATE_KEY_PATH",
    "OPENAI_API_KEY",
}


class AgentRunner(Protocol):
    """Role execution boundary used by the deterministic orchestrator."""

    def run(
        self,
        *,
        prompt: str,
        schema_path: Path,
        model: ModelSelection,
        timeout_seconds: int,
    ) -> CodexRun:
        """Execute one role action and return schema-valid structured output."""
        ...


def sanitized_agent_environment(environment: Mapping[str, str] | None = None) -> dict[str, str]:
    """Remove control-plane and provider secrets before starting an agent process."""
    source = os.environ if environment is None else environment
    cleaned: dict[str, str] = {}
    for key, value in source.items():
        upper = key.upper()
        if key in _SECRET_NAMES or upper.endswith(("_TOKEN", "_SECRET", "_PASSWORD")):
            continue
        if "PRIVATE_KEY" in upper:
            continue
        cleaned[key] = value
    return cleaned


def _redact(text: str, environment: Mapping[str, str]) -> str:
    redacted = text
    for key, value in environment.items():
        upper = key.upper()
        if not value:
            continue
        if (
            key in _SECRET_NAMES
            or upper.endswith(("_TOKEN", "_SECRET", "_PASSWORD"))
            or "PRIVATE_KEY" in upper
        ):
            redacted = redacted.replace(value, "[REDACTED]")
    return redacted


def _load_schema(path: Path) -> JsonObject:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: schema must contain a JSON object")
    return cast(JsonObject, raw)


def validate_output(output: JsonObject, schema_path: Path) -> None:
    """Validate an agent response against the repository contract."""
    validator = Draft202012Validator(_load_schema(schema_path), format_checker=FormatChecker())
    validator.validate(output)


class CodexCliRunner:
    """Invoke Codex CLI as a read-only, ephemeral role execution provider."""

    def __init__(
        self,
        *,
        root: Path,
        executable: str = "codex",
        sandbox: str = "read-only",
        web_search: str = "disabled",
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self._root = root
        self._executable = executable
        self._sandbox = sandbox
        self._web_search = web_search
        self._environment = dict(os.environ if environment is None else environment)

    def run(
        self,
        *,
        prompt: str,
        schema_path: Path,
        model: ModelSelection,
        timeout_seconds: int,
    ) -> CodexRun:
        """Execute one Codex turn and parse its JSONL event stream."""
        command = [
            self._executable,
            "exec",
            "--json",
            "--ephemeral",
            "--sandbox",
            self._sandbox,
            "--cd",
            str(self._root),
            "--model",
            model.model,
            "--config",
            f'model_reasoning_effort="{model.reasoning_effort}"',
            "--config",
            f'web_search="{self._web_search}"',
            "--output-schema",
            str(schema_path),
            "-",
        ]
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                input=prompt,
                text=True,
                capture_output=True,
                check=False,
                timeout=timeout_seconds,
                cwd=self._root,
                env=sanitized_agent_environment(self._environment),
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Codex role run exceeded its elapsed-time budget") from exc
        elapsed_ms = int((time.monotonic() - started) * 1000)

        if completed.returncode != 0:
            detail = _redact(completed.stderr.strip(), self._environment)[-1000:]
            suffix = f": {detail}" if detail else ""
            raise RuntimeError(f"Codex CLI failed with exit code {completed.returncode}{suffix}")

        output: JsonObject | None = None
        thread_id: str | None = None
        usage: Usage | None = None
        turn_completed = False
        fatal_error: str | None = None

        for line in completed.stdout.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                event_raw = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise RuntimeError("Codex CLI emitted malformed JSONL") from exc
            if not isinstance(event_raw, dict):
                continue
            event = cast(dict[str, Any], event_raw)
            event_type = event.get("type")
            if event_type == "thread.started" and isinstance(event.get("thread_id"), str):
                thread_id = cast(str, event["thread_id"])
            elif event_type == "item.completed":
                item = event.get("item")
                if isinstance(item, dict) and item.get("type") == "agent_message":
                    text = item.get("text")
                    if isinstance(text, str):
                        try:
                            parsed = json.loads(text)
                        except json.JSONDecodeError as exc:
                            raise RuntimeError(
                                "Codex final agent message is not valid JSON"
                            ) from exc
                        if not isinstance(parsed, dict):
                            raise RuntimeError("Codex final agent message must be a JSON object")
                        output = cast(JsonObject, parsed)
            elif event_type == "turn.completed":
                usage_raw = event.get("usage")
                if not isinstance(usage_raw, dict):
                    raise RuntimeError("Codex turn.completed event omitted usage telemetry")
                input_tokens = usage_raw.get("input_tokens")
                output_tokens = usage_raw.get("output_tokens")
                if (
                    not isinstance(input_tokens, int)
                    or isinstance(input_tokens, bool)
                    or input_tokens < 0
                    or not isinstance(output_tokens, int)
                    or isinstance(output_tokens, bool)
                    or output_tokens < 0
                ):
                    raise RuntimeError("Codex token usage telemetry is missing or invalid")
                usage = Usage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                )
                turn_completed = True
            elif event_type == "turn.failed":
                error = event.get("error")
                fatal_error = str(error) if error is not None else "Codex turn failed"
            elif event_type == "error":
                fatal_error = str(event.get("message", "Codex event stream failed"))

        if fatal_error is not None:
            raise RuntimeError(_redact(fatal_error, self._environment)[-1000:])
        if not turn_completed:
            raise RuntimeError("Codex CLI exited without a turn.completed event")
        if output is None:
            raise RuntimeError("Codex CLI completed without a structured agent message")
        if usage is None:
            raise RuntimeError("Codex CLI completed without measured token usage")

        try:
            validate_output(output, schema_path)
        except ValidationError as exc:
            raise RuntimeError(
                f"Codex structured output failed schema validation: {exc.message}"
            ) from exc

        return CodexRun(output=output, usage=usage, elapsed_ms=elapsed_ms, thread_id=thread_id)
