"""Authentication routing for user-owned GitHub Projects."""

from pathlib import Path

import pytest

from scripts.orchestrator.config import load_config
from scripts.orchestrator.github_auth import (
    StaticGitHubTokenProvider,
    load_project_token_provider,
)

ROOT = Path(__file__).resolve().parents[1]


def test_user_project_requires_dedicated_classic_pat() -> None:
    config = load_config(ROOT, environment={})
    repository_provider = StaticGitHubTokenProvider("repo-token")

    with pytest.raises(ValueError, match="GITHUB_PROJECT_TOKEN"):
        load_project_token_provider(config, repository_provider, {})

    project_provider = load_project_token_provider(
        config,
        repository_provider,
        {"GITHUB_PROJECT_TOKEN": "project-token"},
    )
    assert project_provider.token() == "project-token"


def test_organization_project_reuses_repository_provider() -> None:
    config = load_config(ROOT, environment={})
    object.__setattr__(config.project, "url", "https://github.com/orgs/example/projects/1")
    repository_provider = StaticGitHubTokenProvider("repo-token")

    project_provider = load_project_token_provider(config, repository_provider, {})

    assert project_provider is repository_provider
