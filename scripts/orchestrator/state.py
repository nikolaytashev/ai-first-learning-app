"""Durable SQLite state and idempotency storage for autonomous workflows."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from scripts.orchestrator.model import CodexRun, JsonObject, ModelSelection


@dataclass(frozen=True)
class WorkflowState:
    """Persisted proposal workflow snapshot."""

    workflow_id: str
    status: str
    proposal_id: str
    proposal: JsonObject | None
    review: JsonObject | None
    issue_number: int | None
    issue_url: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    elapsed_ms: int


class StateStore:
    """SQLite-backed workflow store with explicit side-effect reservations."""

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
                CREATE TABLE IF NOT EXISTS workflows (
                    workflow_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    proposal_id TEXT NOT NULL,
                    proposal_json TEXT,
                    review_json TEXT,
                    issue_number INTEGER,
                    issue_url TEXT,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    elapsed_ms INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS role_runs (
                    workflow_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    profile TEXT NOT NULL,
                    model TEXT NOT NULL,
                    reasoning_effort TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    elapsed_ms INTEGER NOT NULL,
                    output_json TEXT NOT NULL,
                    PRIMARY KEY (workflow_id, role, attempt)
                );
                CREATE TABLE IF NOT EXISTS side_effects (
                    effect_key TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    external_ref TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def create_workflow(self, workflow_id: str, proposal_id: str) -> None:
        """Persist workflow identity before the first nondeterministic role run."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workflows (workflow_id, status, proposal_id)
                VALUES (?, 'running', ?)
                """,
                (workflow_id, proposal_id),
            )

    def latest_waiting(self) -> WorkflowState | None:
        """Return the latest proposal that is already waiting for human action."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM workflows
                WHERE status = 'waiting_human'
                ORDER BY created_at DESC
                LIMIT 1
                """
            ).fetchone()
        return None if row is None else self._from_row(row)

    def get(self, workflow_id: str) -> WorkflowState | None:
        """Read one workflow by durable identifier."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM workflows WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def record_role_run(
        self,
        *,
        workflow_id: str,
        role: str,
        attempt: int,
        model: ModelSelection,
        run: CodexRun,
    ) -> None:
        """Persist measured role output and aggregate workflow telemetry."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO role_runs (
                    workflow_id, role, attempt, profile, model, reasoning_effort,
                    input_tokens, output_tokens, total_tokens, elapsed_ms, output_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_id,
                    role,
                    attempt,
                    model.profile,
                    model.model,
                    model.reasoning_effort,
                    run.usage.input_tokens,
                    run.usage.output_tokens,
                    run.usage.total_tokens,
                    run.elapsed_ms,
                    json.dumps(run.output, sort_keys=True),
                ),
            )
            connection.execute(
                """
                UPDATE workflows
                SET input_tokens = input_tokens + ?,
                    output_tokens = output_tokens + ?,
                    total_tokens = total_tokens + ?,
                    elapsed_ms = elapsed_ms + ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE workflow_id = ?
                """,
                (
                    run.usage.input_tokens,
                    run.usage.output_tokens,
                    run.usage.total_tokens,
                    run.elapsed_ms,
                    workflow_id,
                ),
            )

    def save_proposal(self, workflow_id: str, proposal: JsonObject) -> None:
        """Persist the latest schema-valid PM proposal revision."""
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE workflows
                SET proposal_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE workflow_id = ?
                """,
                (json.dumps(proposal, sort_keys=True), workflow_id),
            )

    def save_review(self, workflow_id: str, review: JsonObject) -> None:
        """Persist the latest schema-valid BA review."""
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE workflows
                SET review_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE workflow_id = ?
                """,
                (json.dumps(review, sort_keys=True), workflow_id),
            )

    def mark_blocked(self, workflow_id: str) -> None:
        """Stop a workflow without publishing side effects."""
        self._set_status(workflow_id, "blocked")

    def mark_waiting(self, workflow_id: str, issue_number: int, issue_url: str) -> None:
        """Persist the human gate after all GitHub side effects have completed."""
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE workflows
                SET status = 'waiting_human', issue_number = ?, issue_url = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE workflow_id = ?
                """,
                (issue_number, issue_url, workflow_id),
            )

    def _set_status(self, workflow_id: str, status: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE workflows
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE workflow_id = ?
                """,
                (status, workflow_id),
            )

    def reserve_effect(self, effect_key: str, workflow_id: str, kind: str) -> str | None:
        """Reserve a side effect before execution and return a prior external ref if known."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status, external_ref FROM side_effects WHERE effect_key = ?",
                (effect_key,),
            ).fetchone()
            if row is not None:
                external_ref = row["external_ref"]
                return external_ref if isinstance(external_ref, str) else None
            connection.execute(
                """
                INSERT INTO side_effects (effect_key, workflow_id, kind, status)
                VALUES (?, ?, ?, 'reserved')
                """,
                (effect_key, workflow_id, kind),
            )
        return None

    def complete_effect(self, effect_key: str, external_ref: str) -> None:
        """Record the durable remote identity after a reserved side effect succeeds."""
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE side_effects
                SET status = 'completed', external_ref = ?, updated_at = CURRENT_TIMESTAMP
                WHERE effect_key = ?
                """,
                (external_ref, effect_key),
            )

    @staticmethod
    def _decode_json(value: object) -> JsonObject | None:
        if not isinstance(value, str):
            return None
        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            raise ValueError("workflow JSON state must contain an object")
        return cast(JsonObject, parsed)

    @classmethod
    def _from_row(cls, row: sqlite3.Row) -> WorkflowState:
        return WorkflowState(
            workflow_id=cast(str, row["workflow_id"]),
            status=cast(str, row["status"]),
            proposal_id=cast(str, row["proposal_id"]),
            proposal=cls._decode_json(row["proposal_json"]),
            review=cls._decode_json(row["review_json"]),
            issue_number=cast(int | None, row["issue_number"]),
            issue_url=cast(str | None, row["issue_url"]),
            input_tokens=cast(int, row["input_tokens"]),
            output_tokens=cast(int, row["output_tokens"]),
            total_tokens=cast(int, row["total_tokens"]),
            elapsed_ms=cast(int, row["elapsed_ms"]),
        )
