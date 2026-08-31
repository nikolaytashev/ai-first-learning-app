"""Subscription usage guard for autonomous Codex workflows."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, cast

import yaml


@dataclass(frozen=True)
class UsageGuardSettings:
    """Configurable reserve thresholds for ChatGPT-authenticated Codex usage."""

    enabled: bool
    query_timeout_seconds: int
    unavailable_policy: str
    five_hour_minimum_remaining_percent: float
    five_hour_expected_window_minutes: int
    five_hour_tolerance_minutes: int
    five_hour_required: bool
    long_term_minimum_remaining_percent: float
    long_term_minimum_window_minutes: int
    long_term_required: bool


@dataclass(frozen=True)
class UsageLimitSnapshot:
    """Normalized account usage limit returned by the Codex app server."""

    name: str
    remaining_percent: float
    duration_minutes: int | None
    resets_at: int | None


@dataclass(frozen=True)
class UsageReadResult:
    """Normalized Codex account usage state."""

    limits: tuple[UsageLimitSnapshot, ...]
    backend_limit_reached: bool
    spend_control_reached: bool


@dataclass(frozen=True)
class UsageGuardDecision:
    """Whether a new autonomous workflow may start."""

    allowed: bool
    reason: str
    limits: tuple[UsageLimitSnapshot, ...]
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a stable JSON-serializable representation for CLI output."""
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "detail": self.detail,
            "limits": [
                {
                    "name": limit.name,
                    "remaining_percent": limit.remaining_percent,
                    "duration_minutes": limit.duration_minutes,
                    "resets_at": limit.resets_at,
                }
                for limit in self.limits
            ],
        }


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return cast(Mapping[str, Any], value)


def _bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def _positive_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _non_negative_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _percent(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{label} must be a number")
    result = float(value)
    if result < 0 or result > 100:
        raise ValueError(f"{label} must be between 0 and 100")
    return result


def load_usage_guard_settings(root: Path) -> UsageGuardSettings:
    """Load checked-in subscription reserve policy from orchestrator.yaml."""
    raw = yaml.safe_load((root / "config/orchestrator.yaml").read_text(encoding="utf-8"))
    runtime = _mapping(raw, "config/orchestrator.yaml")
    guard = _mapping(runtime.get("usage_guard"), "usage_guard")
    five_hour = _mapping(guard.get("five_hour"), "usage_guard.five_hour")
    long_term = _mapping(guard.get("long_term"), "usage_guard.long_term")

    unavailable_policy = guard.get("unavailable_policy")
    if unavailable_policy not in {"block", "allow"}:
        raise ValueError("usage_guard.unavailable_policy must be block or allow")

    return UsageGuardSettings(
        enabled=_bool(guard.get("enabled"), "usage_guard.enabled"),
        query_timeout_seconds=_positive_int(
            guard.get("query_timeout_seconds"),
            "usage_guard.query_timeout_seconds",
        ),
        unavailable_policy=cast(str, unavailable_policy),
        five_hour_minimum_remaining_percent=_percent(
            five_hour.get("minimum_remaining_percent"),
            "usage_guard.five_hour.minimum_remaining_percent",
        ),
        five_hour_expected_window_minutes=_positive_int(
            five_hour.get("expected_window_minutes"),
            "usage_guard.five_hour.expected_window_minutes",
        ),
        five_hour_tolerance_minutes=_non_negative_int(
            five_hour.get("tolerance_minutes"),
            "usage_guard.five_hour.tolerance_minutes",
        ),
        five_hour_required=_bool(
            five_hour.get("required"),
            "usage_guard.five_hour.required",
        ),
        long_term_minimum_remaining_percent=_percent(
            long_term.get("minimum_remaining_percent"),
            "usage_guard.long_term.minimum_remaining_percent",
        ),
        long_term_minimum_window_minutes=_positive_int(
            long_term.get("minimum_window_minutes"),
            "usage_guard.long_term.minimum_window_minutes",
        ),
        long_term_required=_bool(long_term.get("required"), "usage_guard.long_term.required"),
    )


def sanitized_usage_environment(environment: Mapping[str, str] | None = None) -> dict[str, str]:
    """Keep local Codex auth files available without forwarding unrelated secrets."""
    source = os.environ if environment is None else environment
    cleaned: dict[str, str] = {}
    for key, value in source.items():
        upper = key.upper()
        if key == "OPENAI_API_KEY" or upper.endswith(("_TOKEN", "_SECRET", "_PASSWORD")):
            continue
        if "PRIVATE_KEY" in upper:
            continue
        cleaned[key] = value
    return cleaned


def _pump_lines(stream: IO[str], output: queue.Queue[str | None]) -> None:
    try:
        for line in stream:
            output.put(line)
    finally:
        output.put(None)


def _send_message(stream: IO[str], payload: Mapping[str, Any]) -> None:
    stream.write(json.dumps(payload, separators=(",", ":")) + "\n")
    stream.flush()


def _read_response(
    lines: queue.Queue[str | None],
    request_id: int,
    deadline: float,
) -> Mapping[str, Any]:
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("Codex usage query exceeded its timeout")
        try:
            line = lines.get(timeout=remaining)
        except queue.Empty as exc:
            raise RuntimeError("Codex usage query exceeded its timeout") from exc
        if line is None:
            raise RuntimeError("Codex app-server exited before returning account rate limits")
        stripped = line.strip()
        if not stripped:
            continue
        try:
            message = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Codex app-server emitted malformed JSONL") from exc
        if isinstance(message, Mapping) and message.get("id") == request_id:
            return cast(Mapping[str, Any], message)


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def read_codex_account_usage(
    *,
    root: Path,
    executable: str,
    timeout_seconds: int,
    environment: Mapping[str, str] | None = None,
) -> UsageReadResult:
    """Read current ChatGPT rate limits through Codex's supported app-server API."""
    try:
        process = subprocess.Popen(
            [executable, "app-server", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            cwd=root,
            env=sanitized_usage_environment(environment),
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Codex executable not found: {executable}") from exc

    if process.stdin is None or process.stdout is None:
        _stop_process(process)
        raise RuntimeError("Codex app-server stdio transport is unavailable")

    lines: queue.Queue[str | None] = queue.Queue()
    reader = threading.Thread(target=_pump_lines, args=(process.stdout, lines), daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout_seconds

    try:
        _send_message(
            process.stdin,
            {
                "method": "initialize",
                "id": 1,
                "params": {
                    "clientInfo": {
                        "name": "ai_first_learning_orchestrator",
                        "title": "AI First Learning Orchestrator",
                        "version": "1",
                    }
                },
            },
        )
        initialize = _read_response(lines, 1, deadline)
        if initialize.get("error") is not None:
            raise RuntimeError(f"Codex app-server initialization failed: {initialize['error']}")

        _send_message(process.stdin, {"method": "initialized", "params": {}})
        _send_message(process.stdin, {"method": "account/rateLimits/read", "id": 2})
        response = _read_response(lines, 2, deadline)
    except (BrokenPipeError, OSError) as exc:
        raise RuntimeError("Codex app-server closed its stdio transport") from exc
    finally:
        with suppress(OSError):
            process.stdin.close()
        _stop_process(process)
        with suppress(OSError):
            process.stdout.close()

    if response.get("error") is not None:
        raise RuntimeError(f"Codex account rate-limit query failed: {response['error']}")
    result = _mapping(response.get("result"), "account/rateLimits/read.result")
    return normalize_usage_result(result)


def normalize_usage_result(result: Mapping[str, Any]) -> UsageReadResult:
    """Normalize current and future rate-window shapes into stable guard inputs."""
    rate_limits_by_id = result.get("rateLimitsByLimitId")
    selected: Mapping[str, Any]
    if isinstance(rate_limits_by_id, Mapping) and isinstance(
        rate_limits_by_id.get("codex"), Mapping
    ):
        selected = cast(Mapping[str, Any], rate_limits_by_id["codex"])
    else:
        selected = _mapping(result.get("rateLimits"), "rateLimits")

    limits: list[UsageLimitSnapshot] = []
    for name in ("primary", "secondary"):
        raw_window = selected.get(name)
        if raw_window is None:
            continue
        window = _mapping(raw_window, f"rateLimits.{name}")
        used_percent = _percent(window.get("usedPercent"), f"rateLimits.{name}.usedPercent")
        duration_raw = window.get("windowDurationMins")
        if duration_raw is None:
            continue
        duration_minutes = _positive_int(
            duration_raw,
            f"rateLimits.{name}.windowDurationMins",
        )
        resets_at_raw = window.get("resetsAt")
        resets_at = (
            None
            if resets_at_raw is None
            else _positive_int(resets_at_raw, f"rateLimits.{name}.resetsAt")
        )
        limits.append(
            UsageLimitSnapshot(
                name=name,
                remaining_percent=100.0 - used_percent,
                duration_minutes=duration_minutes,
                resets_at=resets_at,
            )
        )

    individual_limit_raw = selected.get("individualLimit")
    if individual_limit_raw is not None:
        individual = _mapping(individual_limit_raw, "rateLimits.individualLimit")
        remaining = _percent(
            individual.get("remainingPercent"),
            "rateLimits.individualLimit.remainingPercent",
        )
        resets_at = _positive_int(
            individual.get("resetsAt"),
            "rateLimits.individualLimit.resetsAt",
        )
        limits.append(
            UsageLimitSnapshot(
                name="individual_monthly_limit",
                remaining_percent=remaining,
                duration_minutes=None,
                resets_at=resets_at,
            )
        )

    return UsageReadResult(
        limits=tuple(limits),
        backend_limit_reached=selected.get("rateLimitReachedType") is not None,
        spend_control_reached=selected.get("spendControlReached") is True,
    )


def evaluate_usage_budget(
    usage: UsageReadResult,
    settings: UsageGuardSettings,
) -> UsageGuardDecision:
    """Apply reserve thresholds without assuming the UI always exposes the same windows."""
    if usage.backend_limit_reached:
        return UsageGuardDecision(False, "backend_limit_reached", usage.limits)
    if usage.spend_control_reached:
        return UsageGuardDecision(False, "spend_control_reached", usage.limits)

    five_hour_limits: list[UsageLimitSnapshot] = []
    long_term_limits: list[UsageLimitSnapshot] = []
    expected = settings.five_hour_expected_window_minutes
    tolerance = settings.five_hour_tolerance_minutes
    for limit in usage.limits:
        if limit.duration_minutes is None:
            if limit.name == "individual_monthly_limit":
                long_term_limits.append(limit)
            continue
        if abs(limit.duration_minutes - expected) <= tolerance:
            five_hour_limits.append(limit)
        if limit.duration_minutes >= settings.long_term_minimum_window_minutes:
            long_term_limits.append(limit)

    for limit in five_hour_limits:
        if limit.remaining_percent < settings.five_hour_minimum_remaining_percent:
            return UsageGuardDecision(False, "five_hour_reserve_reached", usage.limits)

    if settings.five_hour_required and not five_hour_limits:
        return UsageGuardDecision(False, "five_hour_usage_unavailable", usage.limits)

    for limit in long_term_limits:
        if limit.remaining_percent < settings.long_term_minimum_remaining_percent:
            return UsageGuardDecision(False, "long_term_reserve_reached", usage.limits)

    if settings.long_term_required and not long_term_limits:
        return UsageGuardDecision(False, "long_term_usage_unavailable", usage.limits)

    return UsageGuardDecision(True, "usage_available", usage.limits)


def check_usage_budget(
    *,
    root: Path,
    executable: str,
    environment: Mapping[str, str] | None = None,
) -> UsageGuardDecision:
    """Fetch fresh usage on every workflow iteration and decide whether work may start."""
    settings = load_usage_guard_settings(root)
    if not settings.enabled:
        return UsageGuardDecision(True, "usage_guard_disabled", ())
    try:
        usage = read_codex_account_usage(
            root=root,
            executable=executable,
            timeout_seconds=settings.query_timeout_seconds,
            environment=environment,
        )
    except RuntimeError as exc:
        return UsageGuardDecision(
            allowed=settings.unavailable_policy == "allow",
            reason="usage_unavailable",
            limits=(),
            detail=str(exc),
        )
    return evaluate_usage_budget(usage, settings)
