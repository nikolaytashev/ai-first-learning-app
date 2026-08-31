from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from scripts.orchestrator.usage_guard import (
    UsageGuardSettings,
    evaluate_usage_budget,
    normalize_usage_result,
    read_codex_account_usage,
    sanitized_usage_environment,
)


def settings() -> UsageGuardSettings:
    return UsageGuardSettings(
        enabled=True,
        query_timeout_seconds=15,
        unavailable_policy="block",
        five_hour_minimum_remaining_percent=60,
        five_hour_expected_window_minutes=300,
        five_hour_tolerance_minutes=60,
        five_hour_required=False,
        long_term_minimum_remaining_percent=40,
        long_term_minimum_window_minutes=10080,
        long_term_required=True,
    )


def test_blocks_when_five_hour_remaining_is_below_reserve() -> None:
    usage = normalize_usage_result(
        {
            "rateLimits": {
                "primary": {"usedPercent": 41, "windowDurationMins": 300, "resetsAt": 100},
                "secondary": {
                    "usedPercent": 20,
                    "windowDurationMins": 10080,
                    "resetsAt": 200,
                },
            }
        }
    )
    decision = evaluate_usage_budget(usage, settings())
    assert decision.allowed is False
    assert decision.reason == "five_hour_reserve_reached"


def test_allows_exact_reserve_boundaries() -> None:
    usage = normalize_usage_result(
        {
            "rateLimits": {
                "primary": {"usedPercent": 40, "windowDurationMins": 300, "resetsAt": 100},
                "secondary": {
                    "usedPercent": 60,
                    "windowDurationMins": 10080,
                    "resetsAt": 200,
                },
            }
        }
    )
    assert evaluate_usage_budget(usage, settings()).allowed is True


def test_missing_five_hour_window_does_not_block_when_weekly_is_safe() -> None:
    usage = normalize_usage_result(
        {
            "rateLimits": {
                "primary": {"usedPercent": 20, "windowDurationMins": 10080, "resetsAt": 200},
                "secondary": None,
            }
        }
    )
    assert evaluate_usage_budget(usage, settings()).allowed is True


def test_missing_five_hour_window_can_be_made_required() -> None:
    usage = normalize_usage_result(
        {
            "rateLimits": {
                "primary": {"usedPercent": 20, "windowDurationMins": 10080, "resetsAt": 200},
                "secondary": None,
            }
        }
    )
    decision = evaluate_usage_budget(usage, replace(settings(), five_hour_required=True))
    assert decision.allowed is False
    assert decision.reason == "five_hour_usage_unavailable"


def test_monthly_window_replaces_weekly_and_uses_long_term_reserve() -> None:
    usage = normalize_usage_result(
        {
            "rateLimits": {
                "primary": {"usedPercent": 61, "windowDurationMins": 43200, "resetsAt": 300},
                "secondary": None,
            }
        }
    )
    decision = evaluate_usage_budget(usage, settings())
    assert decision.allowed is False
    assert decision.reason == "long_term_reserve_reached"


def test_individual_monthly_limit_is_treated_as_long_term_capacity() -> None:
    usage = normalize_usage_result(
        {
            "rateLimits": {
                "primary": None,
                "secondary": None,
                "individualLimit": {"remainingPercent": 39, "resetsAt": 300},
            }
        }
    )
    decision = evaluate_usage_budget(usage, settings())
    assert decision.allowed is False
    assert decision.reason == "long_term_reserve_reached"


def test_blocks_if_no_long_term_usage_is_available() -> None:
    usage = normalize_usage_result(
        {
            "rateLimits": {
                "primary": {"usedPercent": 10, "windowDurationMins": 300, "resetsAt": 100},
                "secondary": None,
            }
        }
    )
    decision = evaluate_usage_budget(usage, settings())
    assert decision.allowed is False
    assert decision.reason == "long_term_usage_unavailable"


def test_prefers_codex_bucket_from_multi_bucket_response() -> None:
    usage = normalize_usage_result(
        {
            "rateLimits": {
                "primary": {"usedPercent": 99, "windowDurationMins": 300, "resetsAt": 100}
            },
            "rateLimitsByLimitId": {
                "codex": {
                    "primary": {"usedPercent": 10, "windowDurationMins": 300, "resetsAt": 100},
                    "secondary": {
                        "usedPercent": 10,
                        "windowDurationMins": 10080,
                        "resetsAt": 200,
                    },
                }
            },
        }
    )
    assert evaluate_usage_budget(usage, settings()).allowed is True


def test_environment_removes_provider_and_control_plane_secrets() -> None:
    assert sanitized_usage_environment(
        {
            "PATH": "/usr/bin",
            "HOME": "/home/test",
            "CODEX_HOME": "/home/test/.codex",
            "OPENAI_API_KEY": "",
            "GITHUB_TOKEN": "",
        }
    ) == {
        "PATH": "/usr/bin",
        "HOME": "/home/test",
        "CODEX_HOME": "/home/test/.codex",
    }


def test_app_server_handshake_reads_fresh_usage(tmp_path: Path) -> None:
    fake = tmp_path / "codex"
    fake.write_text(
        """#!/usr/bin/env python3
import json
import sys

for line in sys.stdin:
    message = json.loads(line)
    if message.get("method") == "initialize":
        print(json.dumps({"id": message["id"], "result": {}}), flush=True)
    elif message.get("method") == "initialized":
        continue
    elif message.get("method") == "account/rateLimits/read":
        print(json.dumps({
            "id": message["id"],
            "result": {
                "rateLimits": {
                    "primary": {"usedPercent": 25, "windowDurationMins": 300},
                    "secondary": {"usedPercent": 30, "windowDurationMins": 10080}
                }
            }
        }), flush=True)
        break
""",
        encoding="utf-8",
    )
    fake.chmod(0o755)

    usage = read_codex_account_usage(
        root=tmp_path,
        executable=str(fake),
        timeout_seconds=2,
        environment={"PATH": "/usr/bin:/bin"},
    )

    assert [limit.remaining_percent for limit in usage.limits] == [75.0, 70.0]
