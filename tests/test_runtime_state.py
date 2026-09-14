"""Tests for durable runtime-control state."""

from __future__ import annotations

from pathlib import Path

from scripts.orchestrator.runtime_state import RuntimeStateStore


def test_daily_iteration_summary_returns_zeroes_for_empty_day(tmp_path: Path) -> None:
    store = RuntimeStateStore(tmp_path)

    assert store.daily_iteration_summary("2026-09-14") == {
        "date": "2026-09-14",
        "iterations": 0,
        "successes": 0,
        "failures": 0,
        "ai_requests": 0,
        "tasks": 0,
        "pull_requests": 0,
    }
