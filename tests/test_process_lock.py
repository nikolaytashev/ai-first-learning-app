"""Tests for the process-wide autonomous runtime lock."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.orchestrator.process_lock import orchestrator_process_lock


def test_second_process_cannot_enter_same_orchestrator_runtime(tmp_path: Path) -> None:
    script = """
import sys
import time
from pathlib import Path
from scripts.orchestrator.process_lock import orchestrator_process_lock

with orchestrator_process_lock(Path(sys.argv[1])):
    print("locked", flush=True)
    time.sleep(30)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip() == "locked"
        with pytest.raises(RuntimeError, match="another orchestrator runtime already holds"):
            with orchestrator_process_lock(tmp_path):
                pass
    finally:
        process.terminate()
        process.wait(timeout=5)

    with orchestrator_process_lock(tmp_path):
        pass
