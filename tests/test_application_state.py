from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.orchestrator.application_state import ApplicationStateManager


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    )
    return completed.stdout.strip()


def _init_repository(path: Path) -> None:
    path.mkdir()
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.name", "Test User")
    _git(path, "config", "user.email", "test@example.invalid")


def test_refresh_tracks_origin_main_without_fast_forwarding_runtime_checkout(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)

    source = tmp_path / "source"
    _init_repository(source)
    (source / "app.txt").write_text("v1\n", encoding="utf-8")
    _git(source, "add", "app.txt")
    _git(source, "commit", "-m", "v1")
    _git(source, "remote", "add", "origin", str(remote))
    _git(source, "push", "-u", "origin", "main")

    worker = tmp_path / "worker"
    subprocess.run(
        ["git", "clone", "--branch", "main", str(remote), str(worker)],
        check=True,
        capture_output=True,
    )
    trusted_sha = _git(worker, "rev-parse", "HEAD")

    (source / "app.txt").write_text("v2\n", encoding="utf-8")
    _git(source, "add", "app.txt")
    _git(source, "commit", "-m", "v2")
    _git(source, "push", "origin", "main")
    remote_sha = _git(source, "rev-parse", "HEAD")

    manager = ApplicationStateManager(worker, worker / ".orchestrator", "main")
    snapshot = manager.refresh()

    assert snapshot.commit_sha == remote_sha
    assert (snapshot.root / "app.txt").read_text(encoding="utf-8") == "v2\n"
    assert _git(worker, "rev-parse", "HEAD") == trusted_sha
    assert (worker / "app.txt").read_text(encoding="utf-8") == "v1\n"
    assert _git(worker, "branch", "--show-current") == "main"
