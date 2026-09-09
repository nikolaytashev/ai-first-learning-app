"""Tests for renewable GitHub App authentication and credential boundaries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.orchestrator.config import load_config
from scripts.orchestrator.github_auth import (
    GitHubAppTokenProvider,
    StaticGitHubTokenProvider,
    _outside_repository,
)
from scripts.validate_repository import ROOT


class FakeGitHubAppTokenProvider(GitHubAppTokenProvider):
    """Avoid network/JWT work while exercising cache and refresh policy."""

    def __init__(self, *, private_key_path: Path, now: list[datetime]) -> None:
        super().__init__(
            client_id="client-id",
            private_key_path=private_key_path,
            repository_full_name="owner/repo",
            now=lambda: now[0],
        )
        self.mint_calls = 0
        self._clock = now

    def _resolve_installation_id(self) -> int:
        return 42

    def _mint_installation_token(self, installation_id: int) -> tuple[str, datetime]:
        assert installation_id == 42
        self.mint_calls += 1
        return f"installation-token-{self.mint_calls}", self._clock[0] + timedelta(hours=1)


def test_static_token_provider_requires_token() -> None:
    assert StaticGitHubTokenProvider("configured-token").token() == "configured-token"
    with pytest.raises(ValueError, match="GITHUB_TOKEN"):
        StaticGitHubTokenProvider("").token()


def test_repository_config_contains_github_app_client_id() -> None:
    config = load_config(ROOT, {})
    assert config.authorization.github_app_client_id == "Iv23ling22Lvmau5uLUJ"


def test_github_app_token_is_cached_and_refreshed_before_expiry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.orchestrator.github_auth.shutil.which",
        lambda _: "/usr/bin/openssl",
    )
    key = tmp_path / "app.pem"
    key.write_text("test-only-placeholder", encoding="utf-8")
    clock = [datetime(2026, 9, 9, 12, 0, tzinfo=UTC)]
    provider = FakeGitHubAppTokenProvider(private_key_path=key, now=clock)

    first = provider.token()
    assert provider.token() == first
    assert provider.mint_calls == 1

    clock[0] += timedelta(minutes=54)
    assert provider.token() == first
    assert provider.mint_calls == 1

    clock[0] += timedelta(minutes=2)
    assert provider.token() != first
    assert provider.mint_calls == 2


def test_private_key_path_inside_repository_is_rejected(tmp_path: Path) -> None:
    key = tmp_path / "secrets" / "app.pem"
    key.parent.mkdir()
    key.write_text("test-only-placeholder", encoding="utf-8")

    with pytest.raises(ValueError, match="outside the repository"):
        _outside_repository(key, tmp_path)
