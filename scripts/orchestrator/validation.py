"""Select and execute deterministic repository validation profiles for changed files."""

from __future__ import annotations

import fnmatch
import shlex
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from scripts.orchestrator.model import JsonObject

TRUSTED_POLICY_ROOT = Path(__file__).resolve().parents[2]

_PROTECTED_AUTONOMY_PATHS = (
    "orch",
    "AGENTS.md",
    "mission.yaml",
    ".gitignore",
    ".env.example",
    ".secrets.baseline",
    "config/**",
    ".github/workflows/**",
    "schemas/**",
    "scripts/run_orchestrator.py",
    "scripts/validate_repository.py",
    "scripts/orchestrator/**",
    "requirements*.in",
    "requirements*.txt",
    "requirements*.lock",
    "pyproject.toml",
)


@dataclass(frozen=True)
class ValidationCheck:
    """One deterministic command execution result."""

    profile: str
    command: str
    status: str
    exit_code: int
    elapsed_ms: int
    output: str


@dataclass(frozen=True)
class ValidationRun:
    """Combined validation evidence for one implementation candidate."""

    status: str
    checks: tuple[ValidationCheck, ...]

    def as_dict(self) -> JsonObject:
        return {
            "status": self.status,
            "checks": [
                {
                    "profile": check.profile,
                    "command": check.command,
                    "status": check.status,
                    "exit_code": check.exit_code,
                    "elapsed_ms": check.elapsed_ms,
                    "output": check.output,
                }
                for check in self.checks
            ],
        }


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return cast(Mapping[str, Any], value)


def protected_path_violations(changed_files: list[str]) -> list[str]:
    """Return autonomous changes that cross the trusted runtime/guardrail boundary."""
    violations: list[str] = []
    for path in changed_files:
        normalized = path.lstrip("/")
        if any(fnmatch.fnmatch(normalized, pattern) for pattern in _PROTECTED_AUTONOMY_PATHS):
            violations.append(normalized)
    return sorted(set(violations))


def selected_commands(policy_root: Path, changed_files: list[str]) -> list[tuple[str, str]]:
    """Return validation commands selected only from a trusted policy checkout."""
    raw = yaml.safe_load((policy_root / "config/validation.yaml").read_text(encoding="utf-8"))
    document = _mapping(raw, "config/validation.yaml")
    profiles = _mapping(document.get("profiles"), "profiles")
    selection = _mapping(document.get("selection"), "selection")
    always_raw = selection.get("always_run")
    always = set(always_raw) if isinstance(always_raw, list) else set()
    include_matching = selection.get("include_matching_profiles") is True

    selected: list[str] = []
    for name, raw_profile in profiles.items():
        if not isinstance(name, str) or not isinstance(raw_profile, Mapping):
            continue
        patterns_raw = raw_profile.get("path_patterns")
        patterns = (
            [str(pattern) for pattern in patterns_raw] if isinstance(patterns_raw, list) else []
        )
        matches = any(
            fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(f"/{path}", f"/{pattern}")
            for path in changed_files
            for pattern in patterns
        )
        if name in always or (include_matching and matches):
            selected.append(name)

    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name in selected:
        profile = _mapping(profiles.get(name), f"profiles.{name}")
        commands_raw = profile.get("commands")
        if not isinstance(commands_raw, list):
            continue
        for raw_command in commands_raw:
            command = str(raw_command)
            if command not in seen:
                seen.add(command)
                result.append((name, command))
    return result


def run_validation(
    execution_root: Path,
    changed_files: list[str],
    *,
    policy_root: Path | None = None,
    enforce_guardrails: bool = True,
) -> ValidationRun:
    """Execute trusted validation policy in the candidate or trusted integration worktree."""
    violations = protected_path_violations(changed_files) if enforce_guardrails else []
    if violations:
        return ValidationRun(
            "failed",
            (
                ValidationCheck(
                    profile="guardrails",
                    command="protected-path-policy",
                    status="failed",
                    exit_code=1,
                    elapsed_ms=0,
                    output=(
                        "Autonomous implementation may not modify trusted guardrail paths: "
                        + ", ".join(violations)
                    ),
                ),
            ),
        )

    trusted_root = TRUSTED_POLICY_ROOT if policy_root is None else policy_root
    checks: list[ValidationCheck] = []
    for profile, command in selected_commands(trusted_root, changed_files):
        started = time.monotonic()
        try:
            argv = shlex.split(command)
        except ValueError as exc:
            raise ValueError(f"invalid trusted validation command {command!r}: {exc}") from exc
        if not argv:
            raise ValueError(f"trusted validation profile {profile!r} contains an empty command")
        completed = subprocess.run(
            argv,
            cwd=execution_root,
            text=True,
            shell=False,
            capture_output=True,
            check=False,
        )
        elapsed = int((time.monotonic() - started) * 1000)
        output = (completed.stdout + completed.stderr)[-6000:]
        checks.append(
            ValidationCheck(
                profile=profile,
                command=command,
                status="passed" if completed.returncode == 0 else "failed",
                exit_code=completed.returncode,
                elapsed_ms=elapsed,
                output=output,
            )
        )
        if completed.returncode != 0:
            return ValidationRun("failed", tuple(checks))
    return ValidationRun("passed", tuple(checks))
