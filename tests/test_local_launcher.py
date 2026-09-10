"""Contracts for the persistent local orchestrator launcher."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_local_runtime_directory_is_gitignored() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".local/" in gitignore.splitlines()


def test_launcher_loads_local_secrets_and_defaults_to_continuous_run() -> None:
    launcher = (ROOT / "orch").read_text(encoding="utf-8")
    assert ".local/orchestrator.env" not in launcher  # paths are composed from LOCAL_DIR
    assert 'ENV_FILE="$LOCAL_DIR/orchestrator.env"' in launcher
    assert 'KEY_FILE="$LOCAL_DIR/github-app.pem"' in launcher
    assert 'export GITHUB_APP_PRIVATE_KEY_PATH="$KEY_FILE"' in launcher
    assert "set -- run" in launcher
    assert "python3 -m venv" in launcher
