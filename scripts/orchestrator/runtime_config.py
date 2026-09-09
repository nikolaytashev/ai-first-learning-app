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
class ActiveWindowSettings:
    """Local-time window in which the autonomous cadence becomes more active."""

    enabled: bool
    start: time
    end: time
    interval_minutes: int


@dataclass(frozen=True)
class IterationScheduleSettings:
    """Twenty-four-hour cadence settings for autonomous work."""

    timezone: str
    default_interval_minutes: int
    active_window: ActiveWindowSettings


@dataclass(frozen=True)
class ControlPlaneSettings:
    """Polling and GitHub intake settings for the command/control loop."""

    poll_seconds: int
    max_reconciliations_per_iteration: int
    auto_reconcile_human_comments: bool
    command_prefix: str
    epic_title_prefix: str
    feature_title_prefix: str


@dataclass(frozen=True)
class ImplementationWorkflowSettings:
    """Bounded local code-execution settings for one approved task."""

    max_elapsed_seconds: int
    max_corrective_cycles: int
    write_sandbox: str


@dataclass(frozen=True)
class IterationBudgetSettings:
    """Hard resource caps for one autonomous iteration."""

    max_ai_requests: int
    max_tasks: int
    max_pull_requests: int


@dataclass(frozen=True)
class PrioritySettings:
    """Priority and exclusion labels for task-processing workflows."""

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
                "timezone": self.schedule.timezone,
                "default_interval_minutes": self.schedule.default_interval_minutes,
                "active_window": {
                    "enabled": self.schedule.active_window.enabled,
                    "start": self.schedule.active_window.start.strftime("%H:%M"),
                    "end": self.schedule.active_window.end.strftime("%H:%M"),
                    "interval_minutes": self.schedule.active_window.interval_minutes,
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


def _document(root: Path) -> Mapping[str, Any]:
    raw = yaml.safe_load((root / "config/orchestrator.yaml").read_text(encoding="utf-8"))
    return _mapping(raw, "config/orchestrator.yaml")


def _timezone(value: Any, label: str) -> str:
    timezone = _string(value, label)
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown timezone: {timezone}") from exc
    return timezone


def load_control_plane_settings(root: Path) -> ControlPlaneSettings:
    """Load GitHub polling, intake and command defaults."""
    document = _document(root)
    raw = _mapping(document.get("control_plane"), "control_plane")
    intake = _mapping(raw.get("intake"), "control_plane.intake")
    return ControlPlaneSettings(
        poll_seconds=_positive_int(raw.get("poll_seconds"), "control_plane.poll_seconds"),
        max_reconciliations_per_iteration=_positive_int(
            raw.get("max_reconciliations_per_iteration"),
            "control_plane.max_reconciliations_per_iteration",
        ),
        auto_reconcile_human_comments=_bool(
            raw.get("auto_reconcile_human_comments"),
            "control_plane.auto_reconcile_human_comments",
        ),
        command_prefix=_string(raw.get("command_prefix"), "control_plane.command_prefix"),
        epic_title_prefix=_string(
            intake.get("epic_title_prefix"),
            "control_plane.intake.epic_title_prefix",
        ),
        feature_title_prefix=_string(
            intake.get("feature_title_prefix"),
            "control_plane.intake.feature_title_prefix",
        ),
    )


def load_implementation_settings(root: Path) -> ImplementationWorkflowSettings:
    """Load bounded code implementation settings."""
    document = _document(root)
    raw = _mapping(document.get("implementation_workflow"), "implementation_workflow")
    return ImplementationWorkflowSettings(
        max_elapsed_seconds=_positive_int(
            raw.get("max_elapsed_seconds"),
            "implementation_workflow.max_elapsed_seconds",
        ),
        max_corrective_cycles=_positive_int(
            raw.get("max_corrective_cycles"),
            "implementation_workflow.max_corrective_cycles",
        ),
        write_sandbox=_string(raw.get("write_sandbox"), "implementation_workflow.write_sandbox"),
    )


def load_runtime_policy_settings(root: Path) -> RuntimePolicySettings:
    """Load scheduling, budget, priority, stopping and notification defaults."""
    document = _document(root)
    autonomy = _mapping(document.get("autonomy"), "autonomy")

    schedule_raw = _mapping(autonomy.get("schedule"), "autonomy.schedule")
    active_raw = _mapping(schedule_raw.get("active_window"), "autonomy.schedule.active_window")
    timezone = _timezone(schedule_raw.get("timezone"), "autonomy.schedule.timezone")

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
            timezone=timezone,
            default_interval_minutes=_positive_int(
                schedule_raw.get("default_interval_minutes"),
                "autonomy.schedule.default_interval_minutes",
            ),
            active_window=ActiveWindowSettings(
                enabled=_bool(
                    active_raw.get("enabled"),
                    "autonomy.schedule.active_window.enabled",
                ),
                start=_clock(active_raw.get("start"), "autonomy.schedule.active_window.start"),
                end=_clock(active_raw.get("end"), "autonomy.schedule.active_window.end"),
                interval_minutes=_positive_int(
                    active_raw.get("interval_minutes"),
                    "autonomy.schedule.active_window.interval_minutes",
                ),
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
