"""Regression tests for GitHub doctor Project/ruleset verification helpers."""

import pytest

from scripts.orchestrator.github import _project_owner_field, _same_instant


def test_user_project_url_selects_user_graphql_owner() -> None:
    assert _project_owner_field("https://github.com/users/nikolaytashev/projects/1") == "user"


def test_organization_project_url_selects_organization_graphql_owner() -> None:
    assert _project_owner_field("https://github.com/orgs/example/projects/1") == "organization"


def test_unknown_project_url_is_rejected() -> None:
    with pytest.raises(RuntimeError, match="user or organization"):
        _project_owner_field("https://github.com/projects/1")


def test_ruleset_timestamp_compares_same_instant_across_offsets() -> None:
    assert _same_instant(
        "2026-09-09T19:20:05.183+03:00",
        "2026-09-09T16:20:05.183Z",
    )


def test_ruleset_timestamp_detects_actual_change() -> None:
    assert not _same_instant(
        "2026-09-09T19:20:05.183+03:00",
        "2026-09-09T16:21:05.183Z",
    )
