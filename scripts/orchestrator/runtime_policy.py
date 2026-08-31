"""Scheduling, iteration budgets, priority ordering and stop decisions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.orchestrator.codex import AgentRunner
from scripts.orchestrator.model import CodexRun, ModelSelection
from scripts.orchestrator.runtime_config import (
    IterationBudgetSettings,
    PrioritySettings,
    RuntimePolicySettings,
    StoppingSettings,
)


@dataclass(frozen=True)
class PolicyDecision:
    """Whether a policy gate permits a new autonomous iteration."""

    allowed: bool
    reason: str
    detail: str | None = None


@dataclass(frozen=True)
class WorkItem:
    """Minimal sortable work-item projection used by priority policy."""

    identifier: str
    labels: tuple[str, ...]
    sequence: int = 0


@dataclass(frozen=True)
class RepositoryHealthSnapshot:
    """Remote repository conditions relevant to stop policy."""

    build_problems: tuple[str, ...]
    conflicting_pull_requests: tuple[str, ...]
    blocking_pull_requests: tuple[str, ...]


class IterationBudgetExceeded(RuntimeError):
    """Raised before an iteration would exceed a configured hard budget."""


class IterationBudget:
    """Mutable per-iteration counters enforcing checked-in hard caps."""

    def __init__(self, settings: IterationBudgetSettings) -> None:
        self._settings = settings
        self._ai_requests = 0
        self._tasks = 0
        self._pull_requests = 0

    def consume_ai_request(self) -> None:
        """Reserve one AI request before invoking the provider."""
        self._ai_requests = self._consume(
            self._ai_requests,
            self._settings.max_ai_requests,
            "AI request",
        )

    def consume_task(self) -> None:
        """Reserve one processed task before work begins."""
        self._tasks = self._consume(self._tasks, self._settings.max_tasks, "task")

    def consume_pull_request(self) -> None:
        """Reserve one Pull Request before creating it."""
        self._pull_requests = self._consume(
            self._pull_requests,
            self._settings.max_pull_requests,
            "Pull Request",
        )

    @staticmethod
    def _consume(current: int, maximum: int, resource: str) -> int:
        if current >= maximum:
            raise IterationBudgetExceeded(f"iteration {resource} budget exhausted ({maximum})")
        return current + 1

    def as_dict(self) -> dict[str, int]:
        """Return consumed counters for state persistence and reporting."""
        return {
            "ai_requests": self._ai_requests,
            "tasks": self._tasks,
            "pull_requests": self._pull_requests,
        }


class BudgetedAgentRunner:
    """AgentRunner decorator that counts every provider invocation, including retries."""

    def __init__(self, inner: AgentRunner, budget: IterationBudget) -> None:
        self._inner = inner
        self._budget = budget

    def run(
        self,
        *,
        prompt: str,
        schema_path: Path,
        model: ModelSelection,
        timeout_seconds: int,
    ) -> CodexRun:
        """Reserve budget before delegating one agent invocation."""
        self._budget.consume_ai_request()
        return self._inner.run(
            prompt=prompt,
            schema_path=schema_path,
            model=model,
            timeout_seconds=timeout_seconds,
        )


def local_now(settings: RuntimePolicySettings, now_utc: datetime | None = None) -> datetime:
    """Return the policy-local current time from an aware UTC timestamp."""
    current = datetime.now(UTC) if now_utc is None else now_utc
    if current.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    return current.astimezone(ZoneInfo(settings.schedule.working_hours.timezone))


def _inside_working_hours(current: time, start: time, end: time) -> bool:
    if start == end:
        return True
    if start < end:
        return start <= current < end
    return current >= start or current < end


def evaluate_schedule(
    settings: RuntimePolicySettings,
    *,
    now_utc: datetime,
    last_iteration_started_at: datetime | None,
    iterations_today: int,
) -> PolicyDecision:
    """Decide whether cadence, working hours and daily count permit a new iteration."""
    local = local_now(settings, now_utc)
    working = settings.schedule.working_hours
    if working.enabled and not _inside_working_hours(local.time(), working.start, working.end):
        return PolicyDecision(False, "outside_working_hours")
    if iterations_today >= settings.schedule.max_iterations_per_day:
        return PolicyDecision(False, "daily_iteration_limit_reached")
    if last_iteration_started_at is not None:
        if last_iteration_started_at.tzinfo is None:
            raise ValueError("last_iteration_started_at must be timezone-aware")
        next_allowed = last_iteration_started_at + timedelta(
            minutes=settings.schedule.interval_minutes
        )
        if now_utc < next_allowed:
            return PolicyDecision(
                False,
                "iteration_interval_not_elapsed",
                next_allowed.astimezone(UTC).isoformat(),
            )
    return PolicyDecision(True, "schedule_available")


def order_work_items(items: Sequence[WorkItem], settings: PrioritySettings) -> list[WorkItem]:
    """Filter skipped labels and order P0/P1/debt/improvement according to configuration."""
    skipped = {label.casefold() for label in settings.skip_labels}
    ranks = {label.casefold(): position for position, label in enumerate(settings.order)}
    accepted: list[tuple[int, int, WorkItem]] = []
    for item in items:
        labels = {label.casefold() for label in item.labels}
        if labels & skipped:
            continue
        rank = min((ranks[label] for label in labels if label in ranks), default=len(ranks))
        accepted.append((rank, item.sequence, item))
    accepted.sort(key=lambda entry: (entry[0], entry[1], entry[2].identifier))
    return [entry[2] for entry in accepted]


def evaluate_stop_conditions(
    settings: StoppingSettings,
    *,
    consecutive_failures: int,
    repository_health: RepositoryHealthSnapshot | None = None,
) -> PolicyDecision:
    """Apply failure-streak and repository health stop conditions."""
    if consecutive_failures >= settings.max_consecutive_failures:
        return PolicyDecision(False, "consecutive_failure_limit_reached")
    if repository_health is None:
        return PolicyDecision(True, "stop_conditions_clear")
    if settings.stop_on_build_failure and repository_health.build_problems:
        return PolicyDecision(
            False,
            "build_not_passing",
            "; ".join(repository_health.build_problems),
        )
    if settings.stop_on_conflict and repository_health.conflicting_pull_requests:
        return PolicyDecision(
            False,
            "pull_request_conflict",
            "; ".join(repository_health.conflicting_pull_requests),
        )
    if settings.stop_on_blocking_pr and repository_health.blocking_pull_requests:
        return PolicyDecision(
            False,
            "blocking_pull_request",
            "; ".join(repository_health.blocking_pull_requests),
        )
    return PolicyDecision(True, "stop_conditions_clear")


def daily_report_due(settings: RuntimePolicySettings, *, now_utc: datetime) -> bool:
    """Return whether the configured local daily-report time has been reached."""
    if not settings.notifications.enabled or not settings.notifications.daily_report_enabled:
        return False
    return local_now(settings, now_utc).time() >= settings.notifications.daily_report_time
