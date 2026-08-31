"""Read-only GitHub repository health checks for autonomous stop policy."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from scripts.orchestrator.model import OrchestratorConfig
from scripts.orchestrator.runtime_config import StoppingSettings
from scripts.orchestrator.runtime_policy import RepositoryHealthSnapshot

_API = "https://api.github.com"
_SUCCESSFUL_CHECK_CONCLUSIONS = {"success", "neutral", "skipped"}


class RepositoryHealthChecker:
    """Read build and open-PR conditions from GitHub without mutating the repository."""

    def __init__(self, config: OrchestratorConfig, token: str) -> None:
        if not token:
            raise ValueError("GITHUB_TOKEN is required")
        self._config = config
        self._token = token

    def _read(self, method: str, url: str) -> Any:
        request = Request(
            url,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "ai-first-learning-local-orchestrator",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError) as exc:
            raise RuntimeError(f"GitHub repository-health query failed: {url}: {exc}") from exc
        return None if not body else json.loads(body)

    def read(self, settings: StoppingSettings) -> RepositoryHealthSnapshot:
        """Fetch only the remote signals enabled by stop policy."""
        build_problems: list[str] = []
        conflicting: list[str] = []
        blocking: list[str] = []
        repo = self._config.repository.full_name
        branch = self._config.repository.default_branch

        if settings.stop_on_build_failure:
            build_problems.extend(self._build_problems(repo, branch))

        if settings.stop_on_conflict or settings.stop_on_blocking_pr:
            query = urlencode({"state": "open", "base": branch, "per_page": 100})
            raw_pulls = self._read("GET", f"{_API}/repos/{repo}/pulls?{query}")
            if not isinstance(raw_pulls, list):
                raise RuntimeError("GitHub open Pull Request response must be a list")
            blocking_labels = {label.casefold() for label in settings.blocking_pr_labels}
            for raw in raw_pulls:
                if not isinstance(raw, Mapping):
                    continue
                number = raw.get("number")
                if not isinstance(number, int):
                    continue
                title = str(raw.get("title") or "")
                ref = f"#{number} {title}".strip()
                if settings.stop_on_blocking_pr:
                    labels_raw = raw.get("labels")
                    labels = (
                        {
                            str(label.get("name")).casefold()
                            for label in labels_raw
                            if isinstance(label, Mapping)
                            and isinstance(label.get("name"), str)
                        }
                        if isinstance(labels_raw, list)
                        else set()
                    )
                    matched = sorted(labels & blocking_labels)
                    if matched:
                        blocking.append(f"{ref} [{', '.join(matched)}]")
                if settings.stop_on_conflict:
                    detail = self._read("GET", f"{_API}/repos/{repo}/pulls/{number}")
                    if isinstance(detail, Mapping) and detail.get("mergeable") is False:
                        conflicting.append(ref)

        return RepositoryHealthSnapshot(
            build_problems=tuple(build_problems),
            conflicting_pull_requests=tuple(conflicting),
            blocking_pull_requests=tuple(blocking),
        )

    def _build_problems(self, repo: str, branch: str) -> list[str]:
        raw_commit = self._read("GET", f"{_API}/repos/{repo}/commits/{branch}")
        sha = raw_commit.get("sha") if isinstance(raw_commit, Mapping) else None
        if not isinstance(sha, str):
            raise RuntimeError("GitHub default-branch commit response omitted sha")
        raw_checks = self._read(
            "GET",
            f"{_API}/repos/{repo}/commits/{sha}/check-runs?per_page=100",
        )
        checks = raw_checks.get("check_runs") if isinstance(raw_checks, Mapping) else None
        if not isinstance(checks, list):
            raise RuntimeError("GitHub check-runs response omitted check_runs")

        by_name: dict[str, Mapping[str, Any]] = {}
        for raw in checks:
            if not isinstance(raw, Mapping):
                continue
            name = raw.get("name")
            if isinstance(name, str):
                by_name[name] = cast(Mapping[str, Any], raw)

        problems: list[str] = []
        for required in self._config.branch_policy.required_status_checks:
            check = by_name.get(required)
            if check is None:
                problems.append(f"required check {required!r} is missing")
                continue
            status = check.get("status")
            conclusion = check.get("conclusion")
            if status != "completed" or conclusion not in _SUCCESSFUL_CHECK_CONCLUSIONS:
                problems.append(f"required check {required!r} is {status}/{conclusion}")
        return problems
