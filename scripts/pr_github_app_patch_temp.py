"""Temporary branch patcher; removed before merge."""
from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"patch context missing: {path}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    replace(
        "scripts/orchestrator/model.py",
        '''class BranchPolicySettings:\n    """Branch rules that must be verified before autonomous execution."""\n\n    protected_branches: tuple[str, ...]\n    required_status_checks: tuple[str, ...]\n''',
        '''class BranchPolicySettings:\n    """Branch rules that must be verified before autonomous execution."""\n\n    protected_branches: tuple[str, ...]\n    required_status_checks: tuple[str, ...]\n    verified_ruleset_id: int\n    verified_ruleset_updated_at: str\n''',
    )
    replace(
        "scripts/orchestrator/config.py",
        '''    branch_policy = BranchPolicySettings(\n        protected_branches=tuple(cast(list[str], protected_raw)),\n        required_status_checks=tuple(cast(list[str], checks_raw)),\n    )\n''',
        '''    branch_policy = BranchPolicySettings(\n        protected_branches=tuple(cast(list[str], protected_raw)),\n        required_status_checks=tuple(cast(list[str], checks_raw)),\n        verified_ruleset_id=_int(\n            branch_raw.get("verified_ruleset_id"),\n            "branch_policy.verified_ruleset_id",\n        ),\n        verified_ruleset_updated_at=_string(\n            branch_raw.get("verified_ruleset_updated_at"),\n            "branch_policy.verified_ruleset_updated_at",\n        ),\n    )\n''',
    )
    replace(
        "scripts/orchestrator/github.py",
        '''from scripts.orchestrator.model import (\n''',
        '''from scripts.orchestrator.github_auth import (\n    GitHubTokenProvider,\n    StaticGitHubTokenProvider,\n)\nfrom scripts.orchestrator.model import (\n''',
    )
    replace(
        "scripts/orchestrator/github.py",
        '''    def __init__(self, config: OrchestratorConfig, token: str) -> None:\n        if not token:\n            raise ValueError("GITHUB_TOKEN is required")\n        self._config = config\n        self._token = token\n''',
        '''    def __init__(\n        self,\n        config: OrchestratorConfig,\n        token: str | GitHubTokenProvider,\n    ) -> None:\n        self._config = config\n        self._token_provider = (\n            StaticGitHubTokenProvider(token) if isinstance(token, str) else token\n        )\n\n    @property\n    def token_provider(self) -> GitHubTokenProvider:\n        """Return the trusted renewable credential provider used by this client."""\n        return self._token_provider\n''',
    )
    replace(
        "scripts/orchestrator/github.py",
        '''                "Authorization": f"Bearer {self._token}",\n''',
        '''                "Authorization": f"Bearer {self._token_provider.token()}",\n''',
    )
    replace(
        "scripts/orchestrator/github.py",
        '''        rulesets_raw = self._rest("GET", f"/repos/{repo}/rulesets?includes_parents=false")\n        if not isinstance(rulesets_raw, list) or not rulesets_raw:\n            errors.append("repository has no active ruleset to protect main")\n            return errors\n        active_found = False\n        for summary in rulesets_raw:\n            if not isinstance(summary, dict) or summary.get("enforcement") != "active":\n                continue\n            active_found = True\n            ruleset_id = summary.get("id")\n            if not isinstance(ruleset_id, int):\n                continue\n            detail = self._rest("GET", f"/repos/{repo}/rulesets/{ruleset_id}")\n            bypass = detail.get("bypass_actors") if isinstance(detail, dict) else None\n            if isinstance(bypass, list) and bypass:\n                errors.append(f"active ruleset {ruleset_id} contains bypass actors")\n        if not active_found:\n            errors.append("repository has no active ruleset to protect main")\n        return errors\n''',
        '''        ruleset_id = self._config.branch_policy.verified_ruleset_id\n        detail = self._rest("GET", f"/repos/{repo}/rulesets/{ruleset_id}")\n        if not isinstance(detail, dict) or detail.get("enforcement") != "active":\n            errors.append(f"verified ruleset {ruleset_id} is missing or not active")\n            return errors\n        updated_at = detail.get("updated_at")\n        expected_updated_at = self._config.branch_policy.verified_ruleset_updated_at\n        if updated_at != expected_updated_at:\n            errors.append(\n                "verified ruleset changed after human no-bypass verification; "\n                "re-verify it and update branch_policy.verified_ruleset_updated_at"\n            )\n        bypass = detail.get("bypass_actors")\n        if isinstance(bypass, list) and bypass:\n            errors.append(f"verified ruleset {ruleset_id} contains bypass actors")\n        return errors\n''',
    )
    replace(
        "scripts/orchestrator/repository_health.py",
        '''from scripts.orchestrator.model import OrchestratorConfig\n''',
        '''from scripts.orchestrator.github_auth import (\n    GitHubTokenProvider,\n    StaticGitHubTokenProvider,\n)\nfrom scripts.orchestrator.model import OrchestratorConfig\n''',
    )
    replace(
        "scripts/orchestrator/repository_health.py",
        '''    def __init__(self, config: OrchestratorConfig, token: str) -> None:\n        if not token:\n            raise ValueError("GITHUB_TOKEN is required")\n        self._config = config\n        self._token = token\n''',
        '''    def __init__(\n        self,\n        config: OrchestratorConfig,\n        token: str | GitHubTokenProvider,\n    ) -> None:\n        self._config = config\n        self._token_provider = (\n            StaticGitHubTokenProvider(token) if isinstance(token, str) else token\n        )\n''',
    )
    replace(
        "scripts/orchestrator/repository_health.py",
        '''                "Authorization": f"Bearer {self._token}",\n''',
        '''                "Authorization": f"Bearer {self._token_provider.token()}",\n''',
    )
    replace(
        "scripts/orchestrator/implementation.py",
        '''import subprocess\nimport time\nimport uuid\n''',
        '''import subprocess\nimport tempfile\nimport time\nimport uuid\n''',
    )
    replace(
        "scripts/orchestrator/implementation.py",
        '''    def _push(self, worktree: Path, branch: str) -> None:\n        env = dict(os.environ)\n        env["GIT_TERMINAL_PROMPT"] = "0"\n        completed = subprocess.run(\n            ["git", "push", "-u", "origin", f"HEAD:refs/heads/{branch}"],\n            cwd=worktree,\n            text=True,\n            capture_output=True,\n            check=False,\n            env=env,\n        )\n        if completed.returncode != 0:\n            detail = (completed.stdout + completed.stderr)[-2000:]\n            raise RuntimeError(f"git push failed: {detail}")\n''',
        '''    def _push(self, worktree: Path, branch: str) -> None:\n        token = self._github.token_provider.token()\n        self._config.runtime.state_directory.mkdir(parents=True, exist_ok=True)\n        askpass_path: Path | None = None\n        try:\n            with tempfile.NamedTemporaryFile(\n                "w",\n                encoding="utf-8",\n                prefix="git-askpass-",\n                suffix=".sh",\n                dir=self._config.runtime.state_directory,\n                delete=False,\n            ) as handle:\n                handle.write(\n                    "#!/bin/sh\\n"\n                    "case \\"$1\\" in\\n"\n                    "*Username*) printf '%s\\\\n' 'x-access-token' ;;;;\\n"\n                    "*) printf '%s\\\\n' \\"$ORCHESTRATOR_GIT_TOKEN\\" ;;;;\\n"\n                    "esac\\n"\n                )\n                askpass_path = Path(handle.name)\n            askpass_path.chmod(0o700)\n            env = dict(os.environ)\n            env["GIT_TERMINAL_PROMPT"] = "0"\n            env["GIT_ASKPASS"] = str(askpass_path)\n            env["ORCHESTRATOR_GIT_TOKEN"] = token\n            remote = f"https://github.com/{self._config.repository.full_name}.git"\n            completed = subprocess.run(\n                [\n                    "git",\n                    "-c",\n                    "credential.helper=",\n                    "push",\n                    remote,\n                    f"HEAD:refs/heads/{branch}",\n                ],\n                cwd=worktree,\n                text=True,\n                capture_output=True,\n                check=False,\n                env=env,\n            )\n        finally:\n            if askpass_path is not None:\n                askpass_path.unlink(missing_ok=True)\n        if completed.returncode != 0:\n            detail = (completed.stdout + completed.stderr)[-2000:]\n            raise RuntimeError(f"git push failed: {detail}")\n''',
    )
    replace(
        "scripts/run_orchestrator.py",
        '''from scripts.orchestrator.github import GitHubClient\n''',
        '''from scripts.orchestrator.github import GitHubClient\nfrom scripts.orchestrator.github_auth import load_github_token_provider\n''',
    )
    replace(
        "scripts/run_orchestrator.py",
        '''    token = os.environ.get("GITHUB_TOKEN", "")\n    if not token:\n        raise ValueError("GITHUB_TOKEN is required from an external secret provider")\n    github = GitHubClient(config, token)\n''',
        '''    token_provider = load_github_token_provider(config, root=ROOT)\n    github = GitHubClient(config, token_provider)\n''',
    )
    replace(
        "scripts/run_orchestrator.py",
        '''        repository_health = RepositoryHealthChecker(\n            config,\n            os.environ.get("GITHUB_TOKEN", ""),\n        ).read(settings.stopping)\n''',
        '''        repository_health = RepositoryHealthChecker(\n            config,\n            github.token_provider,\n        ).read(settings.stopping)\n''',
    )


if __name__ == "__main__":\n    main()\n