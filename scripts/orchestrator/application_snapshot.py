"""Detached snapshots of the latest merged application state without moving trusted root."""

from __future__ import annotations

import shutil
import subprocess
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ApplicationSnapshot:
    path: Path
    sha: str


def _git(root: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and completed.returncode != 0:
        detail = (completed.stdout + completed.stderr)[-2000:]
        raise RuntimeError(f"git {' '.join(arguments)} failed: {detail}")
    return completed


@contextmanager
def latest_application_snapshot(
    root: Path,
    state_directory: Path,
    default_branch: str,
    *,
    purpose: str,
) -> Iterator[ApplicationSnapshot]:
    """Yield a detached latest-origin snapshot while keeping the orchestrator checkout pinned."""
    _git(root, "fetch", "origin", default_branch)
    remote_ref = f"origin/{default_branch}"
    sha = _git(root, "rev-parse", remote_ref).stdout.strip()
    safe_purpose = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in purpose)[:48]
    worktree = state_directory / "worktrees" / f"snapshot-{safe_purpose}-{uuid.uuid4().hex[:10]}"
    worktree.parent.mkdir(parents=True, exist_ok=True)
    _git(root, "worktree", "add", "--detach", str(worktree), sha)
    try:
        yield ApplicationSnapshot(worktree, sha)
    finally:
        if worktree.exists():
            _git(root, "worktree", "remove", "--force", str(worktree), check=False)
            if worktree.exists():
                shutil.rmtree(worktree, ignore_errors=True)
        _git(root, "worktree", "prune", check=False)
