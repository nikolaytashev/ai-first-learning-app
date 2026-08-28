"""Shared typed records for the local autonomous orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

JsonObject = dict[str, Any]


@dataclass(frozen=True)
class ModelSelection:
    """Resolved Codex model profile for one role action."""

    profile: str
    provider: str
    model: str
    reasoning_effort: str


@dataclass(frozen=True)
class Usage:
    """Normalized token accounting from one Codex role run."""

    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class CodexRun:
    """Structured result and telemetry from a Codex invocation."""

    output: JsonObject
    usage: Usage
    elapsed_ms: int
    thread_id: str | None


@dataclass(frozen=True)
class IssueRef:
    """GitHub issue identity used by the orchestration state machine."""

    number: int
    node_id: str
    url: str


@dataclass(frozen=True)
class RepositorySettings:
    """Repository coordinates used by GitHub control-plane operations."""

    owner: str
    name: str
    default_branch: str

    @property
    def full_name(self) -> str:
        """Return owner/name form expected by GitHub REST endpoints."""
        return f"{self.owner}/{self.name}"


@dataclass(frozen=True)
class ProjectSettings:
    """Configured GitHub Project V2 coordinates and required field contract."""

    owner: str
    number: int | None
    url: str | None
    required_fields: JsonObject


@dataclass(frozen=True)
class AuthorizationSettings:
    """Human and automation identities allowed by the repository policy."""

    human_approvers: tuple[str, ...]
    automation_login: str | None
    automation_identity_type: str | None


@dataclass(frozen=True)
class BranchPolicySettings:
    """Branch rules that must be verified before autonomous execution."""

    protected_branches: tuple[str, ...]
    required_status_checks: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeSettings:
    """Machine-readable local execution controls."""

    state_directory: Path
    proposal_elapsed_seconds: int
    max_role_attempts: int
    max_revision_cycles: int
    malformed_output_corrections: int
    action_token_warning: int
    workflow_token_warning: int
    codex_executable: str
    codex_sandbox: str
    codex_web_search: str


@dataclass(frozen=True)
class OrchestratorConfig:
    """All repository and execution configuration required by the worker."""

    repository: RepositorySettings
    project: ProjectSettings
    authorization: AuthorizationSettings
    branch_policy: BranchPolicySettings
    runtime: RuntimeSettings
    model_profiles: JsonObject
