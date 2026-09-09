"""Renewable GitHub authentication for the trusted orchestrator process."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.orchestrator.model import OrchestratorConfig

_API = "https://api.github.com"
_REFRESH_MARGIN = timedelta(minutes=5)


class GitHubTokenProvider(Protocol):
    """Return a currently valid token without exposing how it is obtained."""

    def token(self) -> str: ...


@dataclass(frozen=True)
class StaticGitHubTokenProvider:
    """Static token provider retained for the restricted-bot identity mode."""

    value: str

    def token(self) -> str:
        if not self.value:
            raise ValueError("GITHUB_TOKEN is required for restricted_bot")
        return self.value


class GitHubAppTokenProvider:
    """Mint and cache short-lived installation tokens for one repository-scoped GitHub App."""

    def __init__(
        self,
        *,
        client_id: str,
        private_key_path: Path,
        repository_full_name: str,
        installation_id: int | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not client_id:
            raise ValueError("GITHUB_APP_CLIENT_ID is required for github_app")
        if not private_key_path.is_file():
            raise ValueError("GITHUB_APP_PRIVATE_KEY_PATH must point to an existing PEM file")
        if shutil.which("openssl") is None:
            raise ValueError("openssl is required for GitHub App authentication")
        self._client_id = client_id
        self._private_key_path = private_key_path
        self._repository_full_name = repository_full_name
        self._installation_id = installation_id
        self._now = now or (lambda: datetime.now(UTC))
        self._cached_token: str | None = None
        self._cached_expiry: datetime | None = None

    def token(self) -> str:
        now = self._now()
        if (
            self._cached_token is not None
            and self._cached_expiry is not None
            and now + _REFRESH_MARGIN < self._cached_expiry
        ):
            return self._cached_token

        installation_id = self._installation_id or self._resolve_installation_id()
        token, expiry = self._mint_installation_token(installation_id)
        self._installation_id = installation_id
        self._cached_token = token
        self._cached_expiry = expiry
        return token

    def _resolve_installation_id(self) -> int:
        raw = self._request_with_jwt(
            "GET",
            f"/repos/{self._repository_full_name}/installation",
        )
        installation_id = raw.get("id") if isinstance(raw, dict) else None
        if not isinstance(installation_id, int) or installation_id < 1:
            raise RuntimeError(
                "GitHub App installation was not found for the configured repository"
            )
        return installation_id

    def _mint_installation_token(self, installation_id: int) -> tuple[str, datetime]:
        raw = self._request_with_jwt(
            "POST",
            f"/app/installations/{installation_id}/access_tokens",
        )
        token = raw.get("token") if isinstance(raw, dict) else None
        expires_at = raw.get("expires_at") if isinstance(raw, dict) else None
        if not isinstance(token, str) or not token:
            raise RuntimeError("GitHub App token response omitted token")
        if not isinstance(expires_at, str):
            raise RuntimeError("GitHub App token response omitted expires_at")
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise RuntimeError("GitHub App token response contained invalid expires_at") from exc
        return token, expiry

    def _request_with_jwt(self, method: str, path: str) -> object:
        jwt = self._jwt()
        request = Request(
            f"{_API}{path}",
            data=b"{}" if method == "POST" else None,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {jwt}",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2026-03-10",
                "User-Agent": "ai-first-learning-local-orchestrator",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError) as exc:
            raise RuntimeError(
                f"GitHub App authentication request failed: {method} {path}"
            ) from exc
        return None if not body else json.loads(body)

    def _jwt(self) -> str:
        now = int(self._now().timestamp())
        header = self._b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode("utf-8"))
        payload = self._b64url(
            json.dumps(
                {"iat": now - 60, "exp": now + 540, "iss": self._client_id},
                separators=(",", ":"),
            ).encode("utf-8")
        )
        signing_input = f"{header}.{payload}".encode("ascii")
        completed = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", str(self._private_key_path)],
            input=signing_input,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0 or not completed.stdout:
            raise RuntimeError("openssl failed to sign the GitHub App JWT")
        signature = self._b64url(completed.stdout)
        return f"{header}.{payload}.{signature}"

    @staticmethod
    def _b64url(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _outside_repository(path: Path, root: Path | None) -> Path:
    resolved = path.expanduser().resolve()
    if root is None:
        return resolved
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return resolved
    raise ValueError("GitHub App private key must be stored outside the repository")


def load_github_token_provider(
    config: OrchestratorConfig,
    environment: Mapping[str, str] | None = None,
    *,
    root: Path | None = None,
) -> GitHubTokenProvider:
    """Resolve the configured GitHub identity without persisting credentials in the repository."""
    env = os.environ if environment is None else environment
    identity_type = config.authorization.automation_identity_type
    if identity_type == "restricted_bot":
        return StaticGitHubTokenProvider(env.get("GITHUB_TOKEN", ""))
    if identity_type != "github_app":
        raise ValueError("GITHUB_AUTOMATION_IDENTITY_TYPE is not configured")

    client_id = env.get("GITHUB_APP_CLIENT_ID", "")
    key_path_raw = env.get("GITHUB_APP_PRIVATE_KEY_PATH", "")
    if not key_path_raw:
        raise ValueError("GITHUB_APP_PRIVATE_KEY_PATH is required for github_app")
    private_key_path = _outside_repository(Path(key_path_raw), root)

    installation_raw = env.get("GITHUB_APP_INSTALLATION_ID", "")
    installation_id: int | None = None
    if installation_raw:
        try:
            installation_id = int(installation_raw)
        except ValueError as exc:
            raise ValueError("GITHUB_APP_INSTALLATION_ID must be an integer") from exc
        if installation_id < 1:
            raise ValueError("GITHUB_APP_INSTALLATION_ID must be a positive integer")

    return GitHubAppTokenProvider(
        client_id=client_id,
        private_key_path=private_key_path,
        repository_full_name=config.repository.full_name,
        installation_id=installation_id,
    )
