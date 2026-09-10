"""Contracts for the persistent local orchestrator launcher."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_local_runtime_directory_is_gitignored() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".local/" in gitignore.splitlines()


def test_launcher_is_valid_bash() -> None:
    completed = subprocess.run(
        ["bash", "-n", str(ROOT / "orch")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_launcher_loads_local_secrets_and_runtime_path() -> None:
    launcher = (ROOT / "orch").read_text(encoding="utf-8")
    assert 'ENV_FILE="$LOCAL_DIR/orchestrator.env"' in launcher
    assert 'KEY_FILE="$LOCAL_DIR/github-app.pem"' in launcher
    assert 'export GITHUB_APP_PRIVATE_KEY_PATH="$KEY_FILE"' in launcher
    assert "ORCHESTRATOR_RUNTIME_PATH" in launcher
    assert "python3 -m venv" in launcher


def test_init_makes_launchd_and_autostart_separate_opt_in_choices() -> None:
    launcher = (ROOT / "orch").read_text(encoding="utf-8")
    assert "Create launchd supervision" in launcher
    assert "Start the orchestrator automatically after login" in launcher
    assert "ORCHESTRATOR_LAUNCHD_ENABLED" in launcher
    assert "ORCHESTRATOR_LAUNCHD_AUTOSTART" in launcher
    assert 'USER_LAUNCH_AGENTS="$HOME/Library/LaunchAgents"' in launcher


def test_launchd_supervises_manual_runs_without_requiring_autostart() -> None:
    launcher = (ROOT / "orch").read_text(encoding="utf-8")
    assert '"KeepAlive": True' in launcher
    assert 'launchctl bootstrap "$LAUNCHD_DOMAIN" "$LAUNCHD_PLIST"' in launcher
    assert 'launchctl kickstart -k "$LAUNCHD_TARGET"' in launcher
    assert 'rm -f "$AUTOSTART_PLIST"' in launcher
    assert "start_launchd" in launcher
    assert "stop_launchd" in launcher
    assert "restart_launchd" in launcher
    assert "status_launchd" in launcher


def test_foreground_run_remains_available_for_debugging() -> None:
    launcher = (ROOT / "orch").read_text(encoding="utf-8")
    assert '"ProgramArguments": [str(root / "orch"), "run"]' in launcher
    assert 'exec "$PYTHON" -m scripts.run_orchestrator "$@"' in launcher
