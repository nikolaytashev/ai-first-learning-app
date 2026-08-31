"""Configurable enable/disable switches layered over the Codex usage guard."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

import yaml

from scripts.orchestrator.usage_guard import (
    UsageGuardDecision,
    UsageGuardSettings,
    evaluate_usage_budget,
    load_usage_guard_settings,
    read_codex_account_usage,
)


@dataclass(frozen=True)
class UsageWindowSwitches:
    """Independent switches for short-term and long-term subscription reserves."""

    five_hour_enabled: bool
    long_term_enabled: bool


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return cast(Mapping[str, Any], value)


def _bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def load_usage_window_switches(root: Path) -> UsageWindowSwitches:
    """Load the optional per-window switches from orchestrator configuration."""
    raw = yaml.safe_load((root / "config/orchestrator.yaml").read_text(encoding="utf-8"))
    document = _mapping(raw, "config/orchestrator.yaml")
    guard = _mapping(document.get("usage_guard"), "usage_guard")
    five_hour = _mapping(guard.get("five_hour"), "usage_guard.five_hour")
    long_term = _mapping(guard.get("long_term"), "usage_guard.long_term")
    return UsageWindowSwitches(
        five_hour_enabled=_bool(five_hour.get("enabled"), "usage_guard.five_hour.enabled"),
        long_term_enabled=_bool(long_term.get("enabled"), "usage_guard.long_term.enabled"),
    )


def apply_usage_window_switches(
    settings: UsageGuardSettings,
    switches: UsageWindowSwitches,
) -> UsageGuardSettings:
    """Return effective thresholds after applying independent enable switches."""
    return replace(
        settings,
        five_hour_minimum_remaining_percent=(
            settings.five_hour_minimum_remaining_percent if switches.five_hour_enabled else 0
        ),
        five_hour_required=settings.five_hour_required and switches.five_hour_enabled,
        long_term_minimum_remaining_percent=(
            settings.long_term_minimum_remaining_percent if switches.long_term_enabled else 0
        ),
        long_term_required=settings.long_term_required and switches.long_term_enabled,
    )


def check_configurable_usage_budget(
    *,
    root: Path,
    executable: str,
    environment: Mapping[str, str] | None = None,
) -> UsageGuardDecision:
    """Fetch fresh usage and apply independently disableable reserve windows."""
    settings = load_usage_guard_settings(root)
    switches = load_usage_window_switches(root)
    if not settings.enabled:
        return UsageGuardDecision(True, "usage_guard_disabled", ())

    effective = apply_usage_window_switches(settings, switches)
    try:
        usage = read_codex_account_usage(
            root=root,
            executable=executable,
            timeout_seconds=settings.query_timeout_seconds,
            environment=environment,
        )
    except RuntimeError as exc:
        return UsageGuardDecision(
            allowed=settings.unavailable_policy == "allow",
            reason="usage_unavailable",
            limits=(),
            detail=str(exc),
        )
    return evaluate_usage_budget(usage, effective)
