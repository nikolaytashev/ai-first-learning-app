from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f"marker not found in {path}: {old[:80]!r}")
    p.write_text(text.replace(old, new, 1))


def replace_in_method(path: str, method_name: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    marker = f"    def {method_name}("
    start = text.index(marker)
    next_def = text.find("\n    def ", start + len(marker))
    end = len(text) if next_def < 0 else next_def
    segment = text[start:end]
    if old not in segment:
        raise SystemExit(f"method marker not found: {method_name}: {old!r}")
    text = text[:start] + segment.replace(old, new) + text[end:]
    p.write_text(text)


# github_auth.py: make static provider error source-aware and add Project token loader.
replace_once(
    "scripts/orchestrator/github_auth.py",
    '''@dataclass(frozen=True)\nclass StaticGitHubTokenProvider:\n    """Static token provider retained for the restricted-bot identity mode."""\n\n    value: str\n\n    def token(self) -> str:\n        if not self.value:\n            raise ValueError("GITHUB_TOKEN is required for restricted_bot")\n        return self.value\n''',
    '''@dataclass(frozen=True)\nclass StaticGitHubTokenProvider:\n    """Static credential provider for externally injected long-lived tokens."""\n\n    value: str\n    variable_name: str = "GITHUB_TOKEN"\n\n    def token(self) -> str:\n        if not self.value:\n            raise ValueError(f"{self.variable_name} is required")\n        return self.value\n''',
)

auth_path = Path("scripts/orchestrator/github_auth.py")
auth_text = auth_path.read_text()
if "def load_project_token_provider(" not in auth_text:
    auth_text += '''\n\ndef load_project_token_provider(\n    config: OrchestratorConfig,\n    repository_provider: GitHubTokenProvider,\n    environment: Mapping[str, str] | None = None,\n) -> GitHubTokenProvider:\n    """Use a classic PAT only for user-owned Project V2 operations.\n\n    GitHub App installation tokens remain the repository identity. GitHub currently\n    requires a user credential with the `project` scope to mutate user-owned Projects.\n    Organization-owned Projects continue to use the repository GitHub App provider.\n    """\n    project_url = config.project.url or ""\n    if "/users/" not in project_url:\n        return repository_provider\n    env = os.environ if environment is None else environment\n    value = env.get("GITHUB_PROJECT_TOKEN", "")\n    if not value:\n        raise ValueError(\n            "GITHUB_PROJECT_TOKEN is required for user-owned GitHub Project; "\n            "use a personal access token (classic) with only the project scope"\n        )\n    return StaticGitHubTokenProvider(value, "GITHUB_PROJECT_TOKEN")\n'''
    auth_path.write_text(auth_text)


# github.py: route Project V2 GraphQL through a dedicated token provider.
replace_once(
    "scripts/orchestrator/github.py",
    '''    def __init__(\n        self,\n        config: OrchestratorConfig,\n        token: str | GitHubTokenProvider,\n    ) -> None:\n        self._config = config\n        self._token_provider = StaticGitHubTokenProvider(token) if isinstance(token, str) else token\n''',
    '''    def __init__(\n        self,\n        config: OrchestratorConfig,\n        token: str | GitHubTokenProvider,\n        project_token: str | GitHubTokenProvider | None = None,\n    ) -> None:\n        self._config = config\n        self._token_provider = StaticGitHubTokenProvider(token) if isinstance(token, str) else token\n        if project_token is None:\n            self._project_token_provider = self._token_provider\n        else:\n            self._project_token_provider = (\n                StaticGitHubTokenProvider(project_token, "GITHUB_PROJECT_TOKEN")\n                if isinstance(project_token, str)\n                else project_token\n            )\n''',
)
replace_once(
    "scripts/orchestrator/github.py",
    '''    def _request(\n        self,\n        method: str,\n        url: str,\n        payload: JsonObject | None = None,\n    ) -> Any:\n        data = None if payload is None else json.dumps(payload).encode("utf-8")\n        request = Request(\n            url,\n            data=data,\n            method=method,\n            headers={\n                "Accept": "application/vnd.github+json",\n                "Authorization": f"Bearer {self._token_provider.token()}",\n''',
    '''    def _request(\n        self,\n        method: str,\n        url: str,\n        payload: JsonObject | None = None,\n        *,\n        token_provider: GitHubTokenProvider | None = None,\n    ) -> Any:\n        data = None if payload is None else json.dumps(payload).encode("utf-8")\n        provider = token_provider or self._token_provider\n        request = Request(\n            url,\n            data=data,\n            method=method,\n            headers={\n                "Accept": "application/vnd.github+json",\n                "Authorization": f"Bearer {provider.token()}",\n''',
)
replace_once(
    "scripts/orchestrator/github.py",
    '''    def _graphql(self, query: str, variables: JsonObject) -> JsonObject:\n        raw = self._request("POST", _GRAPHQL, {"query": query, "variables": variables})\n        if not isinstance(raw, dict):\n            raise RuntimeError("GitHub GraphQL response must be an object")\n        response = cast(JsonObject, raw)\n        errors = response.get("errors")\n        if errors:\n            raise RuntimeError(f"GitHub GraphQL request failed: {errors}")\n        data = response.get("data")\n        if not isinstance(data, dict):\n            raise RuntimeError("GitHub GraphQL response omitted data")\n        return cast(JsonObject, data)\n''',
    '''    def _graphql(self, query: str, variables: JsonObject) -> JsonObject:\n        return self._graphql_with_provider(query, variables, self._token_provider)\n\n    def _project_graphql(self, query: str, variables: JsonObject) -> JsonObject:\n        return self._graphql_with_provider(query, variables, self._project_token_provider)\n\n    def _graphql_with_provider(\n        self,\n        query: str,\n        variables: JsonObject,\n        token_provider: GitHubTokenProvider,\n    ) -> JsonObject:\n        raw = self._request(\n            "POST",\n            _GRAPHQL,\n            {"query": query, "variables": variables},\n            token_provider=token_provider,\n        )\n        if not isinstance(raw, dict):\n            raise RuntimeError("GitHub GraphQL response must be an object")\n        response = cast(JsonObject, raw)\n        errors = response.get("errors")\n        if errors:\n            raise RuntimeError(f"GitHub GraphQL request failed: {errors}")\n        data = response.get("data")\n        if not isinstance(data, dict):\n            raise RuntimeError("GitHub GraphQL response omitted data")\n        return cast(JsonObject, data)\n''',
)
for method in (
    "project_snapshot",
    "_single_select_option_inputs",
    "reconcile_project_contract",
    "add_to_project",
    "find_project_item",
    "update_project_fields",
):
    replace_in_method(
        "scripts/orchestrator/github.py", method, "self._graphql(", "self._project_graphql("
    )


# CLI: construct GitHubClient with separate Project provider everywhere.
replace_once(
    "scripts/run_orchestrator.py",
    "from scripts.orchestrator.github_auth import load_github_token_provider\n",
    '''from scripts.orchestrator.github_auth import (\n    load_github_token_provider,\n    load_project_token_provider,\n)\n''',
)
replace_once(
    "scripts/run_orchestrator.py",
    '''    token_provider = load_github_token_provider(config, root=ROOT)\n    github = GitHubClient(config, token_provider)\n''',
    '''    token_provider = load_github_token_provider(config, root=ROOT)\n    project_provider = load_project_token_provider(config, token_provider)\n    github = GitHubClient(config, token_provider, project_provider)\n''',
)
replace_once(
    "scripts/run_orchestrator.py",
    '''        token_provider = load_github_token_provider(config, root=ROOT)\n        github = GitHubClient(config, token_provider)\n        errors = github.verify_identity_and_scope()\n''',
    '''        token_provider = load_github_token_provider(config, root=ROOT)\n        project_provider = load_project_token_provider(config, token_provider)\n        github = GitHubClient(config, token_provider, project_provider)\n        errors = github.verify_identity_and_scope()\n''',
)


# Environment contract and docs.
replace_once(
    ".env.example",
    '''GITHUB_APP_INSTALLATION_ID=\n\n# Optional notification destination.''',
    '''GITHUB_APP_INSTALLATION_ID=\n\n# User-owned GitHub Projects currently require a personal access token (classic) for\n# mutations. Keep this secret outside the repository and grant only the `project` scope.\nGITHUB_PROJECT_TOKEN=\n\n# Optional notification destination.''',
)
readme = Path("README.md")
readme_text = readme.read_text()
section = '''\n### User-owned GitHub Project authentication\n\nThe repository GitHub App remains the automation identity for repository, Issue, PR and Git\noperations. GitHub currently does not allow an installation token to mutate a user-owned\nProject V2. For `/users/.../projects/...`, inject `GITHUB_PROJECT_TOKEN` as a personal access\ntoken (classic) with only the `project` scope. Do not grant `repo` scope and do not commit the\ntoken. Organization-owned Projects continue to use the GitHub App token.\n\n'''
if "### User-owned GitHub Project authentication" not in readme_text:
    readme_text += section
    readme.write_text(readme_text)


# Existing bootstrap fake must intercept the Project-specific GraphQL path.
replace_once(
    "tests/test_project_bootstrap.py",
    '''    def _graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:\n        self.calls.append((query, variables))\n        return {}\n''',
    '''    def _project_graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:\n        self.calls.append((query, variables))\n        return {}\n''',
)
Path("tests/test_project_auth.py").write_text('''"""Authentication routing for user-owned GitHub Projects."""\n\nfrom pathlib import Path\n\nimport pytest\n\nfrom scripts.orchestrator.config import load_config\nfrom scripts.orchestrator.github_auth import (\n    StaticGitHubTokenProvider,\n    load_project_token_provider,\n)\n\nROOT = Path(__file__).resolve().parents[1]\n\n\ndef test_user_project_requires_dedicated_classic_pat() -> None:\n    config = load_config(ROOT, environment={})\n    repository_provider = StaticGitHubTokenProvider("repo-token")\n\n    with pytest.raises(ValueError, match="GITHUB_PROJECT_TOKEN"):\n        load_project_token_provider(config, repository_provider, {})\n\n    project_provider = load_project_token_provider(\n        config,\n        repository_provider,\n        {"GITHUB_PROJECT_TOKEN": "project-token"},\n    )\n    assert project_provider.token() == "project-token"\n\n\ndef test_organization_project_reuses_repository_provider() -> None:\n    config = load_config(ROOT, environment={})\n    object.__setattr__(config.project, "url", "https://github.com/orgs/example/projects/1")\n    repository_provider = StaticGitHubTokenProvider("repo-token")\n\n    project_provider = load_project_token_provider(config, repository_provider, {})\n\n    assert project_provider is repository_provider\n''')
