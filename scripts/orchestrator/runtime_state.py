"""Durable runtime-control state for repeated autonomous iterations."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from scripts.orchestrator.model import JsonObject


class RuntimeStateStore:
    """Persist scheduling, failure streak, budgets and notification deduplication."""

    def __init__(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self._path = directory / "orchestrator.sqlite3"
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS iterations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    status TEXT NOT NULL,
                    reason TEXT,
                    local_date TEXT NOT NULL,
                    ai_requests INTEGER NOT NULL DEFAULT 0,
                    tasks INTEGER NOT NULL DEFAULT 0,
                    pull_requests INTEGER NOT NULL DEFAULT 0,
                    started_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS notification_events (
                    event_key TEXT PRIMARY KEY,
                    sent_at TEXT NOT NULL
                );
                """
            )

    def start_iteration(
        self,
        local_date: str,
        started_at: datetime | None = None,
    ) -> int:
        """Persist one actual iteration start before any agent work begins."""
        current = _aware_utc(started_at, "started_at")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO iterations (status, local_date, started_at)
                VALUES ('running', ?, ?)
                """,
                (local_date, current.isoformat()),
            )
            row_id = cursor.lastrowid
        if row_id is None:
            raise RuntimeError("failed to persist iteration start")
        return int(row_id)

    def finish_iteration(
        self,
        iteration_id: int,
        *,
        status: str,
        reason: str,
        budget: dict[str, int],
        completed_at: datetime | None = None,
    ) -> None:
        """Persist iteration outcome and consumed hard-budget counters."""
        if status not in {"success", "failed"}:
            raise ValueError("iteration status must be success or failed")
        current = _aware_utc(completed_at, "completed_at")
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE iterations
                SET status = ?, reason = ?, ai_requests = ?, tasks = ?, pull_requests = ?,
                    completed_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    reason,
                    budget.get("ai_requests", 0),
                    budget.get("tasks", 0),
                    budget.get("pull_requests", 0),
                    current.isoformat(),
                    iteration_id,
                ),
            )

    def last_iteration_started_at(self) -> datetime | None:
        """Return the latest real iteration start, excluding manual reset markers."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT started_at FROM iterations
                WHERE status != 'reset'
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return datetime.fromisoformat(cast(str, row["started_at"])).astimezone(UTC)

    def iterations_started_on(self, local_date: str) -> int:
        """Count actual iterations for the configured local calendar day."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count FROM iterations
                WHERE local_date = ? AND status != 'reset'
                """,
                (local_date,),
            ).fetchone()
        return 0 if row is None else int(cast(Any, row["count"]))

    def consecutive_failed_iterations(self) -> int:
        """Count failures since the most recent success or explicit reset marker."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT status FROM iterations
                WHERE status IN ('success', 'failed', 'reset')
                ORDER BY id DESC
                """
            ).fetchall()
        failures = 0
        for row in rows:
            status = cast(str, row["status"])
            if status != "failed":
                break
            failures += 1
        return failures

    def reset_failure_streak(self, local_date: str, reset_at: datetime | None = None) -> None:
        """Record an explicit human resume marker after a stopped failure streak."""
        current = _aware_utc(reset_at, "reset_at")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO iterations (status, reason, local_date, started_at, completed_at)
                VALUES ('reset', 'manual_resume', ?, ?, ?)
                """,
                (local_date, current.isoformat(), current.isoformat()),
            )

    def daily_iteration_summary(self, local_date: str) -> JsonObject:
        """Aggregate outcomes and consumed budgets for one local calendar day."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS iterations,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS successes,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failures,
                    COALESCE(SUM(ai_requests), 0) AS ai_requests,
                    COALESCE(SUM(tasks), 0) AS tasks,
                    COALESCE(SUM(pull_requests), 0) AS pull_requests
                FROM iterations
                WHERE local_date = ? AND status != 'reset'
                """,
                (local_date,),
            ).fetchone()
        if row is None:
            return _empty_summary(local_date)
        return {
            "date": local_date,
            "iterations": int(cast(Any, row["iterations"])),
            "successes": int(cast(Any, row["successes"])),
            "failures": int(cast(Any, row["failures"])),
            "ai_requests": int(cast(Any, row["ai_requests"])),
            "tasks": int(cast(Any, row["tasks"])),
            "pull_requests": int(cast(Any, row["pull_requests"])),
        }

    def notification_sent(self, event_key: str) -> bool:
        """Return whether one deduplicated notification event was already delivered."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM notification_events WHERE event_key = ?",
                (event_key,),
            ).fetchone()
        return row is not None

    def mark_notification_sent(self, event_key: str, sent_at: datetime | None = None) -> None:
        """Persist successful notification delivery for deduplication."""
        current = _aware_utc(sent_at, "sent_at")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO notification_events (event_key, sent_at)
                VALUES (?, ?)
                """,
                (event_key, current.isoformat()),
            )


def _aware_utc(value: datetime | None, label: str) -> datetime:
    current = datetime.now(UTC) if value is None else value
    if current.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware")
    return current.astimezone(UTC)


def _empty_summary(local_date: str) -> JsonObject:
    return {
        "date": local_date,
        "iterations": 0,
        "successes": 0,
        "failures": 0,
        "ai_requests": 0,
        "tasks": 0,
        "pull_requests": 0,
    }
