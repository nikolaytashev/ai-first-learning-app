"""Codex CLI execution adapter with structured-output and telemetry checks."""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
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

_CODEX_OUTPUT_SCHEMA_KEYS = {
    "type",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "enum",
    "anyOf",
    "$defs",
    "$ref",
    "description",
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


class CodexInvocationError(RuntimeError):
    """Codex failure carrying any telemetry observed before the failure."""

    def __init__(
        self,
        message: str,
        *,
        usage: Usage | None,
        elapsed_ms: int,
        thread_id: str | None,
    ) -> None:
        super().__init__(message)
        self.usage = usage
        self.elapsed_ms = elapsed_ms
        self.thread_id = thread_id


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


def _project_codex_schema(value: Any) -> Any:
    """Project full JSON Schema into the conservative Structured Outputs subset."""
    if isinstance(value, list):
        return [_project_codex_schema(item) for item in value]
    if not isinstance(value, dict):
        return value

    projected: dict[str, Any] = {}
    for key, item in value.items():
        if key == "const":
            projected["enum"] = [item]
            continue
        if key == "oneOf":
            if isinstance(item, list):
                projected["anyOf"] = [_project_codex_schema(entry) for entry in item]
            continue
        if key not in _CODEX_OUTPUT_SCHEMA_KEYS:
            continue
        if key in {"properties", "$defs"} and isinstance(item, dict):
            projected[key] = {
                str(name): _project_codex_schema(child) for name, child in item.items()
            }
        elif key in {"items", "anyOf"}:
            projected[key] = _project_codex_schema(item)
        elif key != "additionalProperties":
            projected[key] = item

    properties = projected.get("properties")
    schema_type = projected.get("type")
    object_type = schema_type == "object" or (
        isinstance(schema_type, list) and "object" in schema_type
    )
    if object_type or isinstance(properties, dict):
        projected["additionalProperties"] = False
        if isinstance(properties, dict):
            projected["required"] = list(properties)
    return projected


def codex_output_schema(schema: JsonObject) -> JsonObject:
    """Return a Codex-compatible projection while preserving the full local contract."""
    projected = _project_codex_schema(schema)
    if not isinstance(projected, dict):
        raise ValueError("Codex output schema projection must be a JSON object")
    return cast(JsonObject, projected)


def _codex_failure_detail(
    stdout: str,
    stderr: str,
    environment: Mapping[str, str],
) -> str:
    """Extract useful JSONL error events plus stderr from a failed Codex process."""
    details: list[str] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        if event_type == "error":
            message = event.get("message")
            if message is not None:
                details.append(str(message))
        elif event_type == "turn.failed":
            error = event.get("error")
            if isinstance(error, dict) and error.get("message") is not None:
                details.append(str(error["message"]))
            elif error is not None:
                details.append(str(error))
        elif event_type == "item.completed":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "error":
                message = item.get("message")
                if message is not None:
                    details.append(str(message))

    if stderr.strip():
        details.append(stderr.strip())
    if not details and stdout.strip():
        details.append(stdout.strip())
    return _redact(" | ".join(details), environment)[-2000:]


def _jsonl_telemetry(stdout: str) -> tuple[Usage | None, str | None]:
    """Recover thread and completed-turn usage from a JSONL stream when present."""
    usage: Usage | None = None
    thread_id: str | None = None
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "thread.started" and isinstance(event.get("thread_id"), str):
            thread_id = cast(str, event["thread_id"])
        if event.get("type") != "turn.completed":
            continue
        raw = event.get("usage")
        if not isinstance(raw, dict):
            continue
        input_tokens = raw.get("input_tokens")
        output_tokens = raw.get("output_tokens")
        if (
            isinstance(input_tokens, int)
            and not isinstance(input_tokens, bool)
            and input_tokens >= 0
            and isinstance(output_tokens, int)
            and not isinstance(output_tokens, bool)
            and output_tokens >= 0
        ):
            usage = Usage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            )
    return usage, thread_id


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
        source_schema = _load_schema(schema_path)
        projected_schema = codex_output_schema(source_schema)
        started = time.monotonic()
        try:
            with TemporaryDirectory(prefix="codex-output-schema-") as temporary_directory:
                codex_schema_path = Path(temporary_directory) / schema_path.name
                codex_schema_path.write_text(
                    json.dumps(projected_schema, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
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
                    str(codex_schema_path),
                    "-",
                ]
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
            elapsed_ms = int((time.monotonic() - started) * 1000)
            raw_stdout = exc.stdout or ""
            stdout = (
                raw_stdout.decode("utf-8", errors="replace")
                if isinstance(raw_stdout, bytes)
                else raw_stdout
            )
            timeout_usage, timeout_thread_id = _jsonl_telemetry(stdout)
            raise CodexInvocationError(
                "Codex role run exceeded its elapsed-time budget",
                usage=timeout_usage,
                elapsed_ms=elapsed_ms,
                thread_id=timeout_thread_id,
            ) from exc
        elapsed_ms = int((time.monotonic() - started) * 1000)

        if completed.returncode != 0:
            detail = _codex_failure_detail(
                completed.stdout,
                completed.stderr,
                self._environment,
            )
            suffix = f": {detail}" if detail else ""
            failure_usage, failure_thread_id = _jsonl_telemetry(completed.stdout)
            raise CodexInvocationError(
                f"Codex CLI failed with exit code {completed.returncode}{suffix}",
                usage=failure_usage,
                elapsed_ms=elapsed_ms,
                thread_id=failure_thread_id,
            )

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
            raise CodexInvocationError(
                _redact(fatal_error, self._environment)[-1000:],
                usage=usage,
                elapsed_ms=elapsed_ms,
                thread_id=thread_id,
            )
        if not turn_completed:
            raise CodexInvocationError(
                "Codex CLI exited without a turn.completed event",
                usage=usage,
                elapsed_ms=elapsed_ms,
                thread_id=thread_id,
            )
        if output is None:
            raise CodexInvocationError(
                "Codex CLI completed without a structured agent message",
                usage=usage,
                elapsed_ms=elapsed_ms,
                thread_id=thread_id,
            )
        if usage is None:
            raise CodexInvocationError(
                "Codex CLI completed without measured token usage",
                usage=None,
                elapsed_ms=elapsed_ms,
                thread_id=thread_id,
            )

        try:
            validate_output(output, schema_path)
        except ValidationError as exc:
            raise CodexInvocationError(
                f"Codex structured output failed schema validation: {exc.message}",
                usage=usage,
                elapsed_ms=elapsed_ms,
                thread_id=thread_id,
            ) from exc

        return CodexRun(output=output, usage=usage, elapsed_ms=elapsed_ms, thread_id=thread_id)
