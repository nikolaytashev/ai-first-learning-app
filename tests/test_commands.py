from __future__ import annotations

import pytest

from scripts.orchestrator.commands import parse_commands, validate_command

ACCEPTED = ("analyze", "replan", "approve", "pause", "resume", "cancel", "priority", "rework")


def test_parses_only_namespaced_command_lines() -> None:
    commands = parse_commands(
        "Please change the scope.\n/orch replan\n/orch priority P0",
        prefix="/orch",
        accepted=ACCEPTED,
        comment_id=42,
        actor="nikolaytashev",
    )
    assert [(command.name, command.argument) for command in commands] == [
        ("replan", ""),
        ("priority", "P0"),
    ]


def test_rejects_unknown_command() -> None:
    with pytest.raises(ValueError, match="unknown orchestrator command"):
        parse_commands(
            "/orch destroy",
            prefix="/orch",
            accepted=ACCEPTED,
            comment_id=1,
            actor="nikolaytashev",
        )


def test_validates_scope_and_required_arguments() -> None:
    command = parse_commands(
        "/orch rework Fix the integration boundary",
        prefix="/orch",
        accepted=ACCEPTED,
        comment_id=1,
        actor="nikolaytashev",
    )[0]
    validate_command(command, artifact_type="Task")
    with pytest.raises(ValueError, match="only on Task"):
        validate_command(command, artifact_type="Feature")


def test_priority_is_restricted_to_project_options() -> None:
    command = parse_commands(
        "/orch priority urgent",
        prefix="/orch",
        accepted=ACCEPTED,
        comment_id=1,
        actor="nikolaytashev",
    )[0]
    with pytest.raises(ValueError, match="P0, P1, P2, P3"):
        validate_command(command, artifact_type="Feature")
