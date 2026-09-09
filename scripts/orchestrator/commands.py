"""Parse the namespaced GitHub comment commands accepted by the orchestrator."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OrchestratorCommand:
    """One validated command line from an allow-listed human comment."""

    name: str
    argument: str
    comment_id: int
    actor: str


def parse_commands(
    body: str,
    *,
    prefix: str,
    accepted: tuple[str, ...],
    comment_id: int,
    actor: str,
) -> list[OrchestratorCommand]:
    """Parse exact line-oriented ``/orch`` commands and reject unknown command names."""
    commands: list[OrchestratorCommand] = []
    accepted_set = set(accepted)
    command_prefix = prefix.strip()
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line.startswith(command_prefix):
            continue
        remainder = line[len(command_prefix) :].strip()
        if not remainder:
            raise ValueError(f"{command_prefix} requires a command name")
        name, _, argument = remainder.partition(" ")
        if name not in accepted_set:
            raise ValueError(f"unknown orchestrator command: {name}")
        commands.append(
            OrchestratorCommand(
                name=name,
                argument=argument.strip(),
                comment_id=comment_id,
                actor=actor,
            )
        )
    return commands


def validate_command(command: OrchestratorCommand, *, artifact_type: str) -> None:
    """Enforce command-specific syntax and issue-type constraints before side effects."""
    if command.name == "priority" and command.argument not in {"P0", "P1", "P2", "P3"}:
        raise ValueError("/orch priority requires exactly one of P0, P1, P2, P3")
    if command.name in {"cancel", "rework"} and not command.argument:
        raise ValueError(f"/orch {command.name} requires a reason")
    if command.name == "rework" and artifact_type != "Task":
        raise ValueError("/orch rework is valid only on Task issues")
    if command.name in {"analyze", "replan", "approve"} and artifact_type not in {
        "Epic",
        "Feature",
    }:
        raise ValueError(f"/orch {command.name} is valid only on Epic or Feature issues")
    if command.name in {"pause", "resume", "approve", "analyze", "replan"} and command.argument:
        raise ValueError(f"/orch {command.name} does not accept an argument")
