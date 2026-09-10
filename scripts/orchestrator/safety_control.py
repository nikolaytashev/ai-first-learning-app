"""Pre-process deterministic human control commands before AI usage/stop gates."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from scripts.orchestrator.codex import AgentRunner
from scripts.orchestrator.commands import OrchestratorCommand, parse_commands, validate_command
from scripts.orchestrator.control_plane import (
    ControlPlaneWorkflow,
    ManagedIssue,
    _is_command_only,
    parse_metadata,
)
from scripts.orchestrator.github import GitHubClient
from scripts.orchestrator.model import CodexRun, JsonObject, ModelSelection, OrchestratorConfig
from scripts.orchestrator.runtime_config import ControlPlaneSettings

_SAFETY_COMMANDS = {"pause", "resume", "cancel", "priority", "rework"}
_REGISTRY_NAME = "processed-safety-commands.json"


@dataclass(frozen=True)
class SafetyControlResult:
    """Summary of deterministic control commands handled before any AI work."""

    comments: int
    commands: int

    def as_dict(self) -> JsonObject:
        return {"comments": self.comments, "commands": self.commands}


class _UnavailableAgent(AgentRunner):
    """Guard object proving the safety pre-pass can never invoke an AI role."""

    def run(
        self,
        *,
        prompt: str,
        schema_path: Path,
        model: ModelSelection,
        timeout_seconds: int,
    ) -> CodexRun:
        del prompt, schema_path, model, timeout_seconds
        raise RuntimeError("AI execution is forbidden during the deterministic safety pre-pass")


def _command_key(command: OrchestratorCommand) -> str:
    payload = f"{command.comment_id}\0{command.name}\0{command.argument}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class HardenedControlPlaneWorkflow(ControlPlaneWorkflow):
    """Control plane that remembers commands already handled by the safety pre-pass."""

    def __init__(
        self,
        *,
        root: Path,
        config: OrchestratorConfig,
        settings: ControlPlaneSettings,
        agent: AgentRunner,
        github: GitHubClient,
    ) -> None:
        super().__init__(root=root, config=config, settings=settings, agent=agent, github=github)
        self._safety_registry_path = config.runtime.state_directory / _REGISTRY_NAME

    def _load_safety_registry(self) -> set[str]:
        if not self._safety_registry_path.exists():
            return set()
        try:
            raw = json.loads(self._safety_registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("safety command registry is unreadable") from exc
        if not isinstance(raw, list) or not all(isinstance(value, str) for value in raw):
            raise RuntimeError("safety command registry has invalid data")
        return set(cast(list[str], raw))

    def _save_safety_registry(self, processed: set[str]) -> None:
        self._safety_registry_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._safety_registry_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(sorted(processed), indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self._safety_registry_path)

    def run_safety_commands(self) -> SafetyControlResult:
        """Apply allow-listed deterministic commands without constructing or calling an AI role."""
        processed = self._load_safety_registry()
        comments_processed: set[int] = set()
        commands_processed = 0

        for managed in self._candidate_issues():
            issue = self._github.get_issue(managed.issue.number)
            metadata = parse_metadata(issue.body) or managed.metadata
            artifact_type = cast(str, metadata["type"])
            comments = super()._new_human_comments(issue.number, metadata)

            for comment in comments:
                parsed = parse_commands(
                    comment.body,
                    prefix=self._config.authorization.command_prefix,
                    accepted=self._config.authorization.accepted_commands,
                    comment_id=comment.id,
                    actor=comment.author,
                )
                safety = [command for command in parsed if command.name in _SAFETY_COMMANDS]
                for command in safety:
                    key = _command_key(command)
                    if key in processed:
                        continue
                    validate_command(command, artifact_type=artifact_type)
                    if artifact_type == "Task":
                        self._apply_task_commands(issue, metadata, [command])
                    else:
                        issue, metadata = self._apply_parent_command(issue, metadata, command)
                    processed.add(key)
                    self._save_safety_registry(processed)
                    comments_processed.add(comment.id)
                    commands_processed += 1

        return SafetyControlResult(len(comments_processed), commands_processed)

    def _process(self, managed: ManagedIssue) -> tuple[bool, int]:
        """Run the normal control pass while skipping safety commands already applied early."""
        issue = self._github.get_issue(managed.issue.number)
        metadata = parse_metadata(issue.body) or managed.metadata
        artifact_type = cast(str, metadata["type"])
        comments = self._new_human_comments(issue.number, metadata)
        preprocessed = self._load_safety_registry()
        commands: list[OrchestratorCommand] = []
        for comment in comments:
            parsed = parse_commands(
                comment.body,
                prefix=self._config.authorization.command_prefix,
                accepted=self._config.authorization.accepted_commands,
                comment_id=comment.id,
                actor=comment.author,
            )
            for command in parsed:
                validate_command(command, artifact_type=artifact_type)
                if command.name in _SAFETY_COMMANDS and _command_key(command) in preprocessed:
                    continue
                commands.append(command)

        if artifact_type == "Task":
            self._apply_task_commands(issue, metadata, commands)
            self._advance_comment_cursor(issue.number, metadata, comments)
            return False, len(commands)

        deterministic = [
            command
            for command in commands
            if command.name in {"pause", "resume", "cancel", "priority"}
        ]
        for command in deterministic:
            issue, metadata = self._apply_parent_command(issue, metadata, command)

        if any(command.name == "approve" for command in commands):
            issue, metadata = self._approve(issue, metadata)

        force_analysis = any(command.name in {"analyze", "replan"} for command in commands)
        force_replan = any(command.name == "replan" for command in commands)
        normal_feedback = any(
            not _is_command_only(comment.body, self._config.authorization.command_prefix)
            for comment in comments
        )
        initial = int(metadata.get("revision", 0)) == 0
        should_analyze = (
            metadata.get("paused") is not True
            and (
                initial
                or force_analysis
                or (self._settings.auto_reconcile_human_comments and normal_feedback)
            )
        )
        reconciled = False
        if should_analyze and metadata.get("approval") != "cancelled":
            issue, metadata, analysis = self._analyze(issue, metadata, comments)
            if force_replan or initial or normal_feedback:
                issue, metadata = self._reconcile(issue, metadata, analysis, comments)
                reconciled = True

        self._advance_comment_cursor(issue.number, metadata, comments)
        return reconciled, len(commands)


def run_safety_control(
    *,
    root: Path,
    config: OrchestratorConfig,
    settings: ControlPlaneSettings,
    github: GitHubClient,
) -> SafetyControlResult:
    """Run deterministic GitHub safety/control commands with an AI runner that cannot execute."""
    workflow = HardenedControlPlaneWorkflow(
        root=root,
        config=config,
        settings=settings,
        agent=_UnavailableAgent(),
        github=github,
    )
    return workflow.run_safety_commands()
