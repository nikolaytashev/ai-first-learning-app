from __future__ import annotations

from pathlib import Path

from scripts.orchestrator.usage_guard import (
    evaluate_usage_budget,
    load_usage_guard_settings,
    normalize_usage_result,
)
from scripts.orchestrator.usage_policy import (
    UsageWindowSwitches,
    apply_usage_window_switches,
    load_usage_window_switches,
)


def root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_default_window_switches_are_enabled() -> None:
    switches = load_usage_window_switches(root())
    assert switches.five_hour_enabled is True
    assert switches.long_term_enabled is True


def test_five_hour_reserve_can_be_disabled() -> None:
    settings = load_usage_guard_settings(root())
    effective = apply_usage_window_switches(
        settings,
        UsageWindowSwitches(five_hour_enabled=False, long_term_enabled=True),
    )
    usage = normalize_usage_result(
        {
            "rateLimits": {
                "primary": {"usedPercent": 99, "windowDurationMins": 300, "resetsAt": 100},
                "secondary": {
                    "usedPercent": 20,
                    "windowDurationMins": 10080,
                    "resetsAt": 200,
                },
            }
        }
    )
    assert evaluate_usage_budget(usage, effective).allowed is True


def test_long_term_reserve_can_be_disabled() -> None:
    settings = load_usage_guard_settings(root())
    effective = apply_usage_window_switches(
        settings,
        UsageWindowSwitches(five_hour_enabled=True, long_term_enabled=False),
    )
    usage = normalize_usage_result(
        {
            "rateLimits": {
                "primary": {"usedPercent": 10, "windowDurationMins": 300, "resetsAt": 100},
                "secondary": {
                    "usedPercent": 99,
                    "windowDurationMins": 10080,
                    "resetsAt": 200,
                },
            }
        }
    )
    assert evaluate_usage_budget(usage, effective).allowed is True
