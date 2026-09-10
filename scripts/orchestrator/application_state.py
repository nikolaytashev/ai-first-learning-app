"""Read-only synchronization of the latest merged application state.

The trusted orchestrator checkout is intentionally never checked out, reset or fast-forwarded here.
Only remote refs are fetched and a detached worktree is maintained under the runtime state directory.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ApplicationStateSnapshot:
    """Detached view of the latest fetched default branch."""

    root: Path
    commit_sha: str

    def as_dict(self) -> dict[str, str]:
        return {"root": str(self.root), "commit_sha": self.commit_sha}


class ApplicationStateManager:
    """Maintain a detached origin/default-branch worktree without mutating the runtime checkout."""

    def __init__(self, root: Path, state_directory: Path, default_branch: str) -> None:
        self._root = root
        self._state_directory = state_directory
        self._default_branch = default_branch
        self._snapshot_root = state_directory / "application-state"

    def refresh(self) -> ApplicationStateSnapshot:
        """Fetch and expose the latest remote application state in a detached worktree."""
        self._state_directory.mkdir(parents=True, exist_ok=True)
        self._git(self._root, "fetch", "--quiet", "origin", self._default_branch)
        remote_ref = f"origin/{self._default_branch}"
        commit_sha = self._git(self._root, "rev-parse", remote_ref).stdout.strip()
        if not commit_sha:
            raise RuntimeError(f"could not resolve {remote_ref}")

        if self._snapshot_root.exists():
            current = self._git(
                self._snapshot_root,
                "rev-parse",
                "HEAD",
                check=False,
            )
            if current.returncode == 0 and current.stdout.strip() == commit_sha:
                return ApplicationStateSnapshot(self._snapshot_root, commit_sha)
            self._git(
                self._root,
                "worktree",
                "remove",
                "--force",
                str(self._snapshot_root),
                check=False,
            )
            if self._snapshot_root.exists():
                shutil.rmtree(self._snapshot_root, ignore_errors=True)

        self._git(self._root, "worktree", "prune", check=False)
        self._git(
            self._root,
            "worktree",
            "add",
            "--detach",
            str(self._snapshot_root),
            commit_sha,
        )
        return ApplicationStateSnapshot(self._snapshot_root, commit_sha)

    @staticmethod
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
