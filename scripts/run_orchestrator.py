"""Command-line entry point for the local autonomous orchestrator."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from scripts.orchestrator.codex import CodexCliRunner
from scripts.orchestrator.config import load_config
from scripts.orchestrator.github import GitHubClient
from scripts.orchestrator.proposal import ProposalWorkflow, preflight_errors
from scripts.orchestrator.state import StateStore
from scripts.orchestrator.usage_guard import check_usage_budget, load_usage_guard_settings

ROOT = Path(__file__).resolve().parents[1]


def doctor() -> int:
    """Verify all trusted local and GitHub preconditions without side effects."""
    try:
        config = load_config(ROOT)
        load_usage_guard_settings(ROOT)
        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            raise ValueError("GITHUB_TOKEN is required from an external secret provider")
        github = GitHubClient(config, token)
        errors = preflight_errors(ROOT, config, github)
    except (RuntimeError, ValueError) as exc:
        errors = [str(exc)]

    result = {"status": "ready" if not errors else "blocked", "errors": errors}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 1


def usage() -> int:
    """Show whether current Codex account usage permits a new workflow."""
    try:
        config = load_config(ROOT)
        decision = check_usage_budget(
            root=ROOT,
            executable=config.runtime.codex_executable,
        )
    except (RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2, sort_keys=True))
        return 1

    result = {
        "status": "ready" if decision.allowed else "blocked",
        "usage_guard": decision.as_dict(),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def proposal() -> int:
    """Run one proposal workflow and stop at the human approval gate."""
    try:
        config = load_config(ROOT)
        decision = check_usage_budget(
            root=ROOT,
            executable=config.runtime.codex_executable,
        )
        if not decision.allowed:
            print(
                json.dumps(
                    {
                        "status": "skipped_usage_guard",
                        "usage_guard": decision.as_dict(),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            raise ValueError("GITHUB_TOKEN is required from an external secret provider")
        github = GitHubClient(config, token)
        errors = preflight_errors(ROOT, config, github)
        if errors:
            print(json.dumps({"status": "blocked", "errors": errors}, indent=2, sort_keys=True))
            return 1
        state = StateStore(config.runtime.state_directory)
        agent = CodexCliRunner(
            root=ROOT,
            executable=config.runtime.codex_executable,
            sandbox=config.runtime.codex_sandbox,
            web_search=config.runtime.codex_web_search,
        )
        workflow = ProposalWorkflow(
            root=ROOT,
            config=config,
            state=state,
            agent=agent,
            github=github,
        )
        result = workflow.run()
    except (RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2, sort_keys=True))
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "waiting_human" else 1


def main() -> int:
    """Parse the bounded orchestrator command set."""
    parser = argparse.ArgumentParser(description="AI First Learning local orchestrator")
    parser.add_argument("command", choices=("doctor", "usage", "proposal"))
    args = parser.parse_args()
    if args.command == "doctor":
        return doctor()
    if args.command == "usage":
        return usage()
    return proposal()


if __name__ == "__main__":
    sys.exit(main())
