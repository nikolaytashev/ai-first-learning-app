"""Autonomous backlog generation when the managed product backlog is genuinely empty."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.orchestrator.codex import AgentRunner
from scripts.orchestrator.control_plane import parse_metadata
from scripts.orchestrator.github import GitHubClient
from scripts.orchestrator.model import JsonObject, OrchestratorConfig
from scripts.orchestrator.proposal import ProposalWorkflow
from scripts.orchestrator.state import StateStore


def has_active_managed_backlog(github: GitHubClient) -> bool:
    """Return true while any managed Epic, Feature or Task remains open."""
    for issue in github.list_issues(state="open"):
        metadata = parse_metadata(issue.body)
        if (
            metadata is not None
            and metadata.get("managed") is True
            and metadata.get("type") in {"Epic", "Feature", "Task"}
        ):
            return True
    return False


def generate_next_feature_if_empty(
    *,
    root: Path,
    config: OrchestratorConfig,
    github: GitHubClient,
    agent: AgentRunner,
    context_root: Path | None = None,
) -> JsonObject:
    """Create at most one human-gated Feature proposal when no managed backlog exists."""
    if has_active_managed_backlog(github):
        return {"status": "not_needed"}
    completed_features: list[dict[str, object]] = []
    for issue in github.list_issues(state="closed"):
        metadata = parse_metadata(issue.body)
        if (
            metadata is None
            or metadata.get("managed") is not True
            or metadata.get("type") != "Feature"
            or issue.state_reason != "completed"
        ):
            continue
        completed_features.append(
            {
                "number": issue.number,
                "title": issue.title,
                "completed_specification": issue.body[-6000:],
            }
        )
    completed_features = completed_features[-30:]
    delivered_context = json.dumps(
        {
            "purpose": "Avoid proposing product scope that has already been delivered.",
            "completed_features": completed_features,
        },
        ensure_ascii=False,
        sort_keys=True,
    )

    state = StateStore(config.runtime.state_directory / "backlog")
    waiting = state.latest_waiting()
    if waiting is not None:
        issue_number = waiting.issue_number
        if issue_number is not None:
            issue = github.get_issue(issue_number)
            if issue.state == "open":
                return {
                    "status": "waiting_human",
                    "issue_number": issue_number,
                    "issue_url": issue.url,
                }
        state.mark_completed(waiting.workflow_id)
    return ProposalWorkflow(
        root=root,
        config=config,
        state=state,
        agent=agent,
        github=github,
        supplemental_context=delivered_context,
        context_root=context_root,
    ).run()
