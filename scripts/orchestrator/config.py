"""Configuration loading and model routing for the local orchestrator."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import yaml

from scripts.orchestrator.model import (
    AuthorizationSettings,
    BranchPolicySettings,
    ModelSelection,
    OrchestratorConfig,
    ProjectSettings,
    RepositorySettings,
    RuntimeSettings,
)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return cast(Mapping[str, Any], value)


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _optional_string(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _string(value, label)


def _load_yaml(path: Path) -> Mapping[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return _mapping(raw, str(path))


def _env_or(
    value: str | None,
    env_name: str,
    environment: Mapping[str, str],
) -> str | None:
    override = environment.get(env_name)
    return override if override else value


def _env_int_or(
    value: int | None,
    env_name: str,
    environment: Mapping[str, str],
) -> int | None:
    override = environment.get(env_name)
    if not override:
        return value
    try:
        parsed = int(override)
    except ValueError as exc:
        raise ValueError(f"{env_name} must be an integer") from exc
    return _int(parsed, env_name)


def load_config(
    root: Path,
    environment: Mapping[str, str] | None = None,
) -> OrchestratorConfig:
    """Load checked-in policy plus non-secret local bootstrap overrides."""
    env = os.environ if environment is None else environment
    github = _load_yaml(root / "config/github.yaml")
    runtime_raw = _load_yaml(root / "config/orchestrator.yaml")
    models = _load_yaml(root / "config/model-profiles.yaml")

    repository_raw = _mapping(github.get("repository"), "repository")
    repository = RepositorySettings(
        owner=_string(repository_raw.get("owner"), "repository.owner"),
        name=_string(repository_raw.get("name"), "repository.name"),
        default_branch=_string(
            repository_raw.get("default_branch"),
            "repository.default_branch",
        ),
    )

    project_raw = _mapping(github.get("project"), "project")
    raw_number = project_raw.get("number")
    project_number = None if raw_number is None else _int(raw_number, "project.number")
    project_number = _env_int_or(project_number, "GITHUB_PROJECT_NUMBER", env)
    project_url = _env_or(
        _optional_string(project_raw.get("url"), "project.url"),
        "GITHUB_PROJECT_URL",
        env,
    )
    required_fields = _mapping(
        project_raw.get("required_fields"),
        "project.required_fields",
    )
    project = ProjectSettings(
        owner=_string(project_raw.get("owner"), "project.owner"),
        number=project_number,
        url=project_url,
        required_fields=dict(required_fields),
    )

    authorization_raw = _mapping(github.get("authorization"), "authorization")
    approvers_raw = authorization_raw.get("human_approvers")
    if not isinstance(approvers_raw, list) or not all(
        isinstance(item, str) for item in approvers_raw
    ):
        raise ValueError("authorization.human_approvers must be a string list")
    automation_login = _env_or(
        _optional_string(
            authorization_raw.get("automation_login"),
            "authorization.automation_login",
        ),
        "GITHUB_AUTOMATION_LOGIN",
        env,
    )
    identity_type = _env_or(
        _optional_string(
            authorization_raw.get("automation_identity_type"),
            "authorization.automation_identity_type",
        ),
        "GITHUB_AUTOMATION_IDENTITY_TYPE",
        env,
    )
    if identity_type not in {None, "github_app", "restricted_bot"}:
        raise ValueError("GITHUB_AUTOMATION_IDENTITY_TYPE must be github_app or restricted_bot")
    authorization = AuthorizationSettings(
        human_approvers=tuple(cast(list[str], approvers_raw)),
        automation_login=automation_login,
        automation_identity_type=identity_type,
    )

    branch_raw = _mapping(github.get("branch_policy"), "branch_policy")
    protected_raw = branch_raw.get("protected_branches")
    checks_raw = branch_raw.get("required_status_checks")
    if not isinstance(protected_raw, list) or not all(
        isinstance(item, str) for item in protected_raw
    ):
        raise ValueError("branch_policy.protected_branches must be a string list")
    if not isinstance(checks_raw, list) or not all(isinstance(item, str) for item in checks_raw):
        raise ValueError("branch_policy.required_status_checks must be a string list")
    branch_policy = BranchPolicySettings(
        protected_branches=tuple(cast(list[str], protected_raw)),
        required_status_checks=tuple(cast(list[str], checks_raw)),
    )

    proposal_raw = _mapping(runtime_raw.get("proposal_workflow"), "proposal_workflow")
    state_raw = _mapping(runtime_raw.get("state"), "state")
    codex_raw = _mapping(runtime_raw.get("codex"), "codex")
    state_env = _string(state_raw.get("directory_env"), "state.directory_env")
    default_state = _string(
        state_raw.get("default_directory"),
        "state.default_directory",
    )
    state_directory = root / env.get(state_env, default_state)
    runtime = RuntimeSettings(
        state_directory=state_directory,
        proposal_elapsed_seconds=_int(
            proposal_raw.get("max_elapsed_seconds"),
            "proposal_workflow.max_elapsed_seconds",
        ),
        max_role_attempts=_int(
            proposal_raw.get("max_role_attempts"),
            "proposal_workflow.max_role_attempts",
        ),
        max_revision_cycles=_int(
            proposal_raw.get("max_revision_cycles"),
            "proposal_workflow.max_revision_cycles",
        ),
        malformed_output_corrections=_int(
            proposal_raw.get("malformed_output_corrections"),
            "proposal_workflow.malformed_output_corrections",
        ),
        action_token_warning=_int(
            proposal_raw.get("action_token_warning"),
            "proposal_workflow.action_token_warning",
        ),
        workflow_token_warning=_int(
            proposal_raw.get("workflow_token_warning"),
            "proposal_workflow.workflow_token_warning",
        ),
        codex_executable=_string(codex_raw.get("executable"), "codex.executable"),
        codex_sandbox=_string(codex_raw.get("sandbox"), "codex.sandbox"),
        codex_web_search=_string(codex_raw.get("web_search"), "codex.web_search"),
    )

    if (
        models.get("configuration_status") != "approved"
        or models.get("execution_enabled") is not True
    ):
        raise ValueError("model profiles are not approved for execution")

    return OrchestratorConfig(
        repository=repository,
        project=project,
        authorization=authorization,
        branch_policy=branch_policy,
        runtime=runtime,
        model_profiles=dict(models),
    )


def select_model(
    config: OrchestratorConfig,
    role: str,
    action: str,
    attempt: int,
) -> ModelSelection:
    """Select the lowest approved profile, escalating only after repeated failure."""
    defaults = _mapping(config.model_profiles.get("role_defaults"), "role_defaults")
    role_config = _mapping(defaults.get(role), f"role_defaults.{role}")
    profiles = _mapping(config.model_profiles.get("profiles"), "profiles")
    overrides = role_config.get("action_overrides")
    profile_name: str
    if isinstance(overrides, Mapping) and action in overrides:
        profile_name = _string(
            overrides[action],
            f"role_defaults.{role}.action_overrides.{action}",
        )
    else:
        profile_name = _string(
            role_config.get("default"),
            f"role_defaults.{role}.default",
        )

    allowed_raw = role_config.get("allowed_profiles")
    if not isinstance(allowed_raw, list) or not all(isinstance(item, str) for item in allowed_raw):
        raise ValueError(f"role_defaults.{role}.allowed_profiles must be a string list")
    allowed = cast(list[str], allowed_raw)
    if attempt >= 3:
        current_index = allowed.index(profile_name)
        if current_index + 1 < len(allowed):
            profile_name = allowed[current_index + 1]

    profile = _mapping(profiles.get(profile_name), f"profiles.{profile_name}")
    return ModelSelection(
        profile=profile_name,
        provider=_string(
            profile.get("provider"),
            f"profiles.{profile_name}.provider",
        ),
        model=_string(profile.get("model"), f"profiles.{profile_name}.model"),
        reasoning_effort=_string(
            profile.get("reasoning_effort"),
            f"profiles.{profile_name}.reasoning_effort",
        ),
    )
