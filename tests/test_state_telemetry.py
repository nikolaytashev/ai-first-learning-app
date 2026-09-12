"""Tests for durable telemetry from failed agent attempts."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.orchestrator.model import ModelSelection, Usage
from scripts.orchestrator.state import StateStore


def test_failed_role_attempt_is_persisted_and_counted(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    workflow_id = "wf-test"
    store.create_workflow(workflow_id, "FP-1234")
    model = ModelSelection("balanced", "openai", "gpt-test", "medium")
    usage = Usage(input_tokens=100, output_tokens=20, total_tokens=120)

    store.record_role_failure(
        workflow_id=workflow_id,
        role="product_manager:revision-1",
        attempt=1,
        model=model,
        usage=usage,
        elapsed_ms=2500,
        error="schema validation failed",
    )

    state = store.get(workflow_id)
    assert state is not None
    assert state.input_tokens == 100
    assert state.output_tokens == 20
    assert state.total_tokens == 120
    assert state.elapsed_ms == 2500

    with sqlite3.connect(tmp_path / "orchestrator.sqlite3") as connection:
        row = connection.execute(
            "SELECT status, error, input_tokens, output_tokens FROM role_runs "
            "WHERE workflow_id = ? AND role = ? AND attempt = 1",
            (workflow_id, "product_manager:revision-1"),
        ).fetchone()
    assert row == ("failed", "schema validation failed", 100, 20)


def test_existing_role_runs_table_is_migrated(tmp_path: Path) -> None:
    database = tmp_path / "orchestrator.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE role_runs (
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
            )
            """
        )

    StateStore(tmp_path)

    with sqlite3.connect(database) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(role_runs)")}
    assert {"status", "error"} <= columns
