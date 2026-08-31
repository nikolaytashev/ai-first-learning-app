"""Checked-in configuration for repeated autonomous execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from scripts.orchestrator.model import JsonObject


@dataclass(frozen=True)
class WorkingHoursSettings:
    """Local-time window in which new autonomous iterations may begin."""

    enabled: bool
    timezone: str
    start: time
    end: time


@dataclass(frozen=True)
class IterationScheduleSettings:
    """Cadence and daily-cap settings for autonomous work."""

    interval_minutes: int
    max_iterations_per_day: int
    working_hours: WorkingHoursSettings


@dataclass(frozen=True)
class IterationBudgetSettings:
    """Hard resource caps for one autonomous iteration."""

    max_ai_requests: int
    max_tasks: int
    max_pull_requests: int


@dataclass(frozen=True)
class PrioritySettings:
    """Priority and exclusion labels for future task-processing workflows."""

    order: tuple[str, ...]
    skip_labels: tuple[str, ...]


@dataclass(frozen=True)
class StoppingSettings:
    """Conditions that pause autonomous work before another iteration starts."""

    max_consecutive_failures: int
    stop_on_build_failure: bool
    stop_on_conflict: bool
    stop_on_blocking_pr: bool
    blocking_pr_labels: tuple[str, ...]


@dataclass(frozen=True)
class NotificationSettings:
    """Notification delivery and event-selection policy."""

    enabled: bool
    provider: str
    webhook_url_env: str
    daily_report_enabled: bool
    daily_report_time: time
    critical_error_enabled: bool
    usage_limit_stop_enabled: bool
    autonomy_stopped_enabled: bool


@dataclass(frozen=True)
class RuntimePolicySettings:
    """Complete checked-in policy for repeated autonomous execution."""

    schedule: IterationScheduleSettings
    budget: IterationBudgetSettings
    priorities: PrioritySettings
    stopping: StoppingSettings
    notifications: NotificationSettings

    def as_dict(self) -> JsonObject:
        """Return a stable JSON-serializable representation for CLI inspection."""
        return {
            "schedule": {
                "interval_minutes": self.schedule.interval_minutes,
                "max_iterations_per_day": self.schedule.max_iterations_per_day,
                "working_hours": {
                    "enabled": self.schedule.working_hours.enabled,
                    "timezone": self.schedule.working_hours.timezone,
                    "start": self.schedule.working_hours.start.strftime("%H:%M"),
                    "end": self.schedule.working_hours.end.strftime("%H:%M"),
                },
            },
            "iteration_budget": {
                "max_ai_requests": self.budget.max_ai_requests,
                "max_tasks": self.budget.max_tasks,
                "max_pull_requests": self.budget.max_pull_requests,
            },
            "priorities": {
                "order": list(self.priorities.order),
                "skip_labels": list(self.priorities.skip_labels),
            },
            "stopping": {
                "max_consecutive_failures": self.stopping.max_consecutive_failures,
                "stop_on_build_failure": self.stopping.stop_on_build_failure,
                "stop_on_conflict": self.stopping.stop_on_conflict,
                "stop_on_blocking_pr": self.stopping.stop_on_blocking_pr,
                "blocking_pr_labels": list(self.stopping.blocking_pr_labels),
            },
            "notifications": {
                "enabled": self.notifications.enabled,
                "provider": self.notifications.provider,
                "webhook_url_env": self.notifications.webhook_url_env,
                "daily_report": {
                    "enabled": self.notifications.daily_report_enabled,
                    "time": self.notifications.daily_report_time.strftime("%H:%M"),
                },
                "critical_error": self.notifications.critical_error_enabled,
                "usage_limit_stop": self.notifications.usage_limit_stop_enabled,
                "autonomy_stopped": self.notifications.autonomy_stopped_enabled,
            },
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


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _string_list(value: Any, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{label} must be a string list")
    if not value and not allow_empty:
        raise ValueError(f"{label} must not be empty")
    return tuple(cast(list[str], value))


def _clock(value: Any, label: str) -> time:
    raw = _string(value, label)
    try:
        return time.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{label} must be HH:MM") from exc


def load_runtime_policy_settings(root: Path) -> RuntimePolicySettings:
    """Load scheduling, budget, priority, stopping and notification defaults."""
    raw = yaml.safe_load((root / "config/orchestrator.yaml").read_text(encoding="utf-8"))
    document = _mapping(raw, "config/orchestrator.yaml")
    autonomy = _mapping(document.get("autonomy"), "autonomy")

    schedule_raw = _mapping(autonomy.get("schedule"), "autonomy.schedule")
    working_raw = _mapping(schedule_raw.get("working_hours"), "autonomy.schedule.working_hours")
    timezone = _string(working_raw.get("timezone"), "autonomy.schedule.working_hours.timezone")
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown timezone: {timezone}") from exc

    budget_raw = _mapping(autonomy.get("iteration_budget"), "autonomy.iteration_budget")
    priorities_raw = _mapping(autonomy.get("priorities"), "autonomy.priorities")
    stopping_raw = _mapping(autonomy.get("stopping"), "autonomy.stopping")
    notifications_raw = _mapping(autonomy.get("notifications"), "autonomy.notifications")
    daily_raw = _mapping(
        notifications_raw.get("daily_report"),
        "autonomy.notifications.daily_report",
    )

    provider = _string(notifications_raw.get("provider"), "autonomy.notifications.provider")
    if provider not in {"auto", "console", "webhook"}:
        raise ValueError("autonomy.notifications.provider must be auto, console or webhook")

    return RuntimePolicySettings(
        schedule=IterationScheduleSettings(
            interval_minutes=_positive_int(
                schedule_raw.get("interval_minutes"),
                "autonomy.schedule.interval_minutes",
            ),
            max_iterations_per_day=_positive_int(
                schedule_raw.get("max_iterations_per_day"),
                "autonomy.schedule.max_iterations_per_day",
            ),
            working_hours=WorkingHoursSettings(
                enabled=_bool(
                    working_raw.get("enabled"),
                    "autonomy.schedule.working_hours.enabled",
                ),
                timezone=timezone,
                start=_clock(working_raw.get("start"), "autonomy.schedule.working_hours.start"),
                end=_clock(working_raw.get("end"), "autonomy.schedule.working_hours.end"),
            ),
        ),
        budget=IterationBudgetSettings(
            max_ai_requests=_positive_int(
                budget_raw.get("max_ai_requests"),
                "autonomy.iteration_budget.max_ai_requests",
            ),
            max_tasks=_positive_int(
                budget_raw.get("max_tasks"),
                "autonomy.iteration_budget.max_tasks",
            ),
            max_pull_requests=_positive_int(
                budget_raw.get("max_pull_requests"),
                "autonomy.iteration_budget.max_pull_requests",
            ),
        ),
        priorities=PrioritySettings(
            order=_string_list(priorities_raw.get("order"), "autonomy.priorities.order"),
            skip_labels=_string_list(
                priorities_raw.get("skip_labels"),
                "autonomy.priorities.skip_labels",
                allow_empty=True,
            ),
        ),
        stopping=StoppingSettings(
            max_consecutive_failures=_positive_int(
                stopping_raw.get("max_consecutive_failures"),
                "autonomy.stopping.max_consecutive_failures",
            ),
            stop_on_build_failure=_bool(
                stopping_raw.get("stop_on_build_failure"),
                "autonomy.stopping.stop_on_build_failure",
            ),
            stop_on_conflict=_bool(
                stopping_raw.get("stop_on_conflict"),
                "autonomy.stopping.stop_on_conflict",
            ),
            stop_on_blocking_pr=_bool(
                stopping_raw.get("stop_on_blocking_pr"),
                "autonomy.stopping.stop_on_blocking_pr",
            ),
            blocking_pr_labels=_string_list(
                stopping_raw.get("blocking_pr_labels"),
                "autonomy.stopping.blocking_pr_labels",
                allow_empty=True,
            ),
        ),
        notifications=NotificationSettings(
            enabled=_bool(notifications_raw.get("enabled"), "autonomy.notifications.enabled"),
            provider=provider,
            webhook_url_env=_string(
                notifications_raw.get("webhook_url_env"),
                "autonomy.notifications.webhook_url_env",
            ),
            daily_report_enabled=_bool(
                daily_raw.get("enabled"),
                "autonomy.notifications.daily_report.enabled",
            ),
            daily_report_time=_clock(
                daily_raw.get("time"),
                "autonomy.notifications.daily_report.time",
            ),
            critical_error_enabled=_bool(
                notifications_raw.get("critical_error"),
                "autonomy.notifications.critical_error",
            ),
            usage_limit_stop_enabled=_bool(
                notifications_raw.get("usage_limit_stop"),
                "autonomy.notifications.usage_limit_stop",
            ),
            autonomy_stopped_enabled=_bool(
                notifications_raw.get("autonomy_stopped"),
                "autonomy.notifications.autonomy_stopped",
            ),
        ),
    )
