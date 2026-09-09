"""Select and execute deterministic repository validation profiles for changed files."""

from __future__ import annotations

import fnmatch
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from scripts.orchestrator.model import JsonObject


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


def selected_commands(root: Path, changed_files: list[str]) -> list[tuple[str, str]]:
    """Return de-duplicated validation commands selected by config/validation.yaml."""
    raw = yaml.safe_load((root / "config/validation.yaml").read_text(encoding="utf-8"))
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


def run_validation(root: Path, changed_files: list[str]) -> ValidationRun:
    """Execute every selected command without shell interpolation beyond the checked-in command."""
    checks: list[ValidationCheck] = []
    for profile, command in selected_commands(root, changed_files):
        started = time.monotonic()
        completed = subprocess.run(
            command,
            cwd=root,
            text=True,
            shell=True,
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
