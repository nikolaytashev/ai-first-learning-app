from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.orchestrator.runtime_config import PrioritySettings, load_runtime_policy_settings
from scripts.orchestrator.runtime_policy import (
    IterationBudget,
    IterationBudgetExceeded,
    RepositoryHealthSnapshot,
    WorkItem,
    daily_report_due,
    evaluate_schedule,
    evaluate_stop_conditions,
    order_work_items,
)
from scripts.orchestrator.runtime_state import RuntimeStateStore


def root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_loads_checked_in_runtime_defaults() -> None:
    settings = load_runtime_policy_settings(root())
    assert settings.schedule.interval_minutes == 30
    assert settings.schedule.max_iterations_per_day == 8
    assert settings.schedule.working_hours.timezone == "Europe/Sofia"
    assert settings.budget.max_ai_requests == 12
    assert settings.budget.max_tasks == 3
    assert settings.budget.max_pull_requests == 1
    assert settings.priorities.order[:2] == ("P0", "P1")
    assert settings.stopping.max_consecutive_failures == 3


def test_schedule_blocks_before_interval_elapsed() -> None:
    settings = load_runtime_policy_settings(root())
    now = datetime(2026, 8, 31, 10, 0, tzinfo=UTC)
    decision = evaluate_schedule(
        settings,
        now_utc=now,
        last_iteration_started_at=now - timedelta(minutes=29),
        iterations_today=1,
    )
    assert decision.allowed is False
    assert decision.reason == "iteration_interval_not_elapsed"


def test_schedule_allows_after_interval_inside_working_hours() -> None:
    settings = load_runtime_policy_settings(root())
    now = datetime(2026, 8, 31, 10, 0, tzinfo=UTC)
    decision = evaluate_schedule(
        settings,
        now_utc=now,
        last_iteration_started_at=now - timedelta(minutes=30),
        iterations_today=1,
    )
    assert decision.allowed is True


def test_schedule_blocks_outside_working_hours() -> None:
    settings = load_runtime_policy_settings(root())
    now = datetime(2026, 8, 31, 4, 0, tzinfo=UTC)
    decision = evaluate_schedule(
        settings,
        now_utc=now,
        last_iteration_started_at=None,
        iterations_today=0,
    )
    assert decision.allowed is False
    assert decision.reason == "outside_working_hours"


def test_schedule_blocks_daily_iteration_cap() -> None:
    settings = load_runtime_policy_settings(root())
    now = datetime(2026, 8, 31, 10, 0, tzinfo=UTC)
    decision = evaluate_schedule(
        settings,
        now_utc=now,
        last_iteration_started_at=None,
        iterations_today=8,
    )
    assert decision.allowed is False
    assert decision.reason == "daily_iteration_limit_reached"


def test_iteration_budget_is_hard_cap() -> None:
    settings = load_runtime_policy_settings(root())
    budget = IterationBudget(settings.budget)
    for _ in range(settings.budget.max_ai_requests):
        budget.consume_ai_request()
    with pytest.raises(IterationBudgetExceeded):
        budget.consume_ai_request()
    assert budget.as_dict()["ai_requests"] == settings.budget.max_ai_requests


def test_priority_order_and_skip_labels_are_case_insensitive() -> None:
    settings = PrioritySettings(
        order=("P0", "P1", "technical-debt", "enhancement"),
        skip_labels=("blocked",),
    )
    items = [
        WorkItem("enhancement", ("enhancement",), 1),
        WorkItem("p1", ("p1",), 2),
        WorkItem("ignored", ("P0", "BLOCKED"), 0),
        WorkItem("p0", ("P0",), 3),
        WorkItem("debt", ("technical-debt",), 4),
    ]
    assert [item.identifier for item in order_work_items(items, settings)] == [
        "p0",
        "p1",
        "debt",
        "enhancement",
    ]


def test_stop_after_configured_consecutive_failures() -> None:
    settings = load_runtime_policy_settings(root())
    decision = evaluate_stop_conditions(
        settings.stopping,
        consecutive_failures=settings.stopping.max_consecutive_failures,
    )
    assert decision.allowed is False
    assert decision.reason == "consecutive_failure_limit_reached"


def test_stop_on_build_conflict_and_blocking_pr() -> None:
    settings = load_runtime_policy_settings(root())
    health = RepositoryHealthSnapshot(
        build_problems=("repository-validation failed",),
        conflicting_pull_requests=("#7 conflict",),
        blocking_pull_requests=("#8 blocked",),
    )
    decision = evaluate_stop_conditions(
        settings.stopping,
        consecutive_failures=0,
        repository_health=health,
    )
    assert decision.allowed is False
    assert decision.reason == "build_not_passing"


def test_daily_report_becomes_due_at_configured_local_time() -> None:
    settings = load_runtime_policy_settings(root())
    assert (
        daily_report_due(
            settings,
            now_utc=datetime(2026, 8, 31, 18, 0, tzinfo=UTC),
        )
        is True
    )


def test_state_tracks_daily_limits_failure_streak_and_notifications(tmp_path: Path) -> None:
    state = RuntimeStateStore(tmp_path)
    started = datetime(2026, 8, 31, 10, 0, tzinfo=UTC)
    first = state.start_iteration("2026-08-31", started)
    state.finish_iteration(
        first,
        status="failed",
        reason="boom",
        budget={"ai_requests": 2, "tasks": 1, "pull_requests": 0},
        completed_at=started + timedelta(minutes=1),
    )
    second = state.start_iteration("2026-08-31", started + timedelta(minutes=31))
    state.finish_iteration(
        second,
        status="failed",
        reason="boom again",
        budget={"ai_requests": 3, "tasks": 1, "pull_requests": 1},
        completed_at=started + timedelta(minutes=32),
    )

    assert state.iterations_started_on("2026-08-31") == 2
    assert state.consecutive_failed_iterations() == 2
    assert state.daily_iteration_summary("2026-08-31") == {
        "date": "2026-08-31",
        "iterations": 2,
        "successes": 0,
        "failures": 2,
        "ai_requests": 5,
        "tasks": 2,
        "pull_requests": 1,
    }
    assert state.notification_sent("usage:1") is False
    state.mark_notification_sent("usage:1", started)
    assert state.notification_sent("usage:1") is True

    state.reset_failure_streak("2026-08-31", started + timedelta(hours=1))
    assert state.consecutive_failed_iterations() == 0
    assert state.iterations_started_on("2026-08-31") == 2
