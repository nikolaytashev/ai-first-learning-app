"""Security contracts for deterministic autonomous validation."""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

import yaml

from scripts.orchestrator.validation import protected_path_violations, run_validation


def _write_policy(root: Path, command: str) -> None:
    config = root / "config"
    config.mkdir(parents=True)
    (config / "validation.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "profiles": {
                    "repository": {
                        "path_patterns": ["**"],
                        "commands": [command],
                    }
                },
                "selection": {
                    "always_run": ["repository"],
                    "include_matching_profiles": True,
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_validation_policy_comes_from_trusted_root_not_candidate_worktree(tmp_path: Path) -> None:
    policy_root = tmp_path / "trusted"
    worktree = tmp_path / "candidate"
    worktree.mkdir()

    python = shlex.quote(sys.executable)
    _write_policy(
        policy_root,
        f"{python} -c \"from pathlib import Path; Path('trusted-ran').write_text('yes')\"",
    )
    candidate_command = (
        f"{python} -c \"from pathlib import Path; Path('candidate-policy-ran').write_text('bad')\""
    )
    _write_policy(worktree, candidate_command)

    result = run_validation(worktree, ["docs/example.md"], policy_root=policy_root)

    assert result.status == "passed"
    assert (worktree / "trusted-ran").read_text(encoding="utf-8") == "yes"
    assert not (worktree / "candidate-policy-ran").exists()


def test_validation_commands_do_not_use_a_shell(tmp_path: Path) -> None:
    policy_root = tmp_path / "trusted"
    worktree = tmp_path / "candidate"
    worktree.mkdir()
    python = shlex.quote(sys.executable)
    _write_policy(
        policy_root,
        (
            f"{python} -c \"from pathlib import Path; Path('argv-ran').write_text('yes')\" "
            "&& touch shell-interpolation-ran"
        ),
    )

    result = run_validation(worktree, ["docs/example.md"], policy_root=policy_root)

    assert result.status == "passed"
    assert (worktree / "argv-ran").exists()
    assert not (worktree / "shell-interpolation-ran").exists()


def test_protected_guardrail_paths_fail_before_validation_commands(tmp_path: Path) -> None:
    worktree = tmp_path / "candidate"
    worktree.mkdir()

    result = run_validation(worktree, ["scripts/orchestrator/validation.py"])

    assert result.status == "failed"
    assert result.checks[0].profile == "guardrails"
    assert result.checks[0].command == "protected-path-policy"
    assert "scripts/orchestrator/validation.py" in result.checks[0].output


def test_protected_path_contract_covers_runtime_ci_and_credentials() -> None:
    changed = [
        "orch",
        "AGENTS.md",
        ".gitignore",
        ".secrets.baseline",
        "config/orchestrator.yaml",
        ".github/workflows/ci.yml",
        "schemas/agent-review.schema.json",
        "scripts/run_orchestrator.py",
        "scripts/validate_repository.py",
        "scripts/orchestrator/github_auth.py",
        "requirements-dev.lock",
    ]

    assert protected_path_violations(changed) == sorted(changed)
    product_files = ["mobile/lib/main.dart", "backend/App.cs", "docs/lesson.md"]
    assert protected_path_violations(product_files) == []
