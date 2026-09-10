"""Cross-process lock preventing concurrent autonomous orchestrator runtimes."""

from __future__ import annotations

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO


@contextmanager
def orchestrator_process_lock(state_directory: Path) -> Iterator[None]:
    """Hold an exclusive process lock for one side-effectful orchestrator runtime."""
    state_directory.mkdir(parents=True, exist_ok=True)
    path = state_directory / "orchestrator.lock"
    handle: TextIO = path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.seek(0)
            owner = handle.read().strip() or "unknown process"
            raise RuntimeError(
                f"another orchestrator runtime already holds {path} ({owner})"
            ) from exc
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()}\n")
        handle.flush()
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
