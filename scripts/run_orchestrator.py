"""Command-line entry point for the local autonomous orchestrator."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from scripts.orchestrator.codex import CodexCliRunner
from scripts.orchestrator.config import load_config
from scripts.orchestrator.github import GitHubClient
from scripts.orchestrator.notifications import Notifier
from scripts.orchestrator.proposal import ProposalWorkflow, preflight_errors
from scripts.orchestrator.repository_health import RepositoryHealthChecker
from scripts.orchestrator.runtime_config import RuntimePolicySettings, load_runtime_policy_settings
from scripts.orchestrator.runtime_policy import (
    BudgetedAgentRunner,
    IterationBudget,
    daily_report_due,
    evaluate_schedule,
    evaluate_stop_conditions,
    local_now,
)
from scripts.orchestrator.runtime_state import RuntimeStateStore
from scripts.orchestrator.state import StateStore, WorkflowState
from scripts.orchestrator.usage_guard import load_usage_guard_settings
from scripts.orchestrator.usage_policy import (
    check_configurable_usage_budget,
    load_usage_window_switches,
)

ROOT = Path(__file__).resolve().parents[1]


def _print(value: dict[str, object]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _workflow_result(state: WorkflowState) -> dict[str, object]:
    return {
        "workflow_id": state.workflow_id,
        "status": state.status,
        "proposal_id": state.proposal_id,
        "issue_number": state.issue_number,
        "issue_url": state.issue_url,
        "usage": {
            "input_tokens": state.input_tokens,
            "output_tokens": state.output_tokens,
            "total_tokens": state.total_tokens,
        },
        "elapsed_ms": state.elapsed_ms,
    }


def _notify_once(
    state: RuntimeStateStore,
    notifier: Notifier,
    *,
    event_key: str,
    kind: str,
    message: str,
    payload: dict[str, object],
    now_utc: datetime,
) -> None:
    if state.notification_sent(event_key):
        return
    if notifier.send(kind, message, payload):
        state.mark_notification_sent(event_key, now_utc)


def _emit_daily_report_if_due(
    state: RuntimeStateStore,
    notifier: Notifier,
    *,
    settings: RuntimePolicySettings,
    now_utc: datetime,
) -> None:
    if not daily_report_due(settings, now_utc=now_utc):
        return
    local_date = local_now(settings, now_utc).date().isoformat()
    summary = state.daily_iteration_summary(local_date)
    _notify_once(
        state,
        notifier,
        event_key=f"daily-report:{local_date}",
        kind="daily_report",
        message=f"Autonomous daily report for {local_date}",
        payload=summary,
        now_utc=now_utc,
    )


def doctor() -> int:
    """Verify all trusted local and GitHub preconditions without side effects."""
    try:
        config = load_config(ROOT)
        load_usage_guard_settings(ROOT)
        load_runtime_policy_settings(ROOT)
        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            raise ValueError("GITHUB_TOKEN is required from an external secret provider")
        github = GitHubClient(config, token)
        errors = preflight_errors(ROOT, config, github)
    except (RuntimeError, ValueError) as exc:
        errors = [str(exc)]

    result = {"status": "ready" if not errors else "blocked", "errors": errors}
    _print(result)
    return 0 if not errors else 1


def usage() -> int:
    """Show whether current Codex account usage permits a new workflow."""
    try:
        config = load_config(ROOT)
        decision = check_configurable_usage_budget(
            root=ROOT,
            executable=config.runtime.codex_executable,
        )
    except (RuntimeError, ValueError) as exc:
        _print({"status": "failed", "error": str(exc)})
        return 1

    result = {
        "status": "ready" if decision.allowed else "blocked",
        "usage_guard": decision.as_dict(),
    }
    _print(result)
    return 0


def policy() -> int:
    """Print the resolved autonomous runtime policy without starting work."""
    try:
        settings = load_runtime_policy_settings(ROOT)
        usage_settings = load_usage_guard_settings(ROOT)
        usage_switches = load_usage_window_switches(ROOT)
    except ValueError as exc:
        _print({"status": "failed", "error": str(exc)})
        return 1
    _print(
        {
            "status": "ready",
            "autonomy": settings.as_dict(),
            "usage_guard": {
                "enabled": usage_settings.enabled,
                "five_hour_enabled": usage_switches.five_hour_enabled,
                "long_term_enabled": usage_switches.long_term_enabled,
            },
        }
    )
    return 0


def resume() -> int:
    """Clear the consecutive-failure stop after a human has addressed the problem."""
    try:
        config = load_config(ROOT)
        settings = load_runtime_policy_settings(ROOT)
        state = RuntimeStateStore(config.runtime.state_directory)
        now_utc = datetime.now(UTC)
        local_date = local_now(settings, now_utc).date().isoformat()
        state.reset_failure_streak(local_date, now_utc)
    except (RuntimeError, ValueError) as exc:
        _print({"status": "failed", "error": str(exc)})
        return 1
    _print({"status": "resumed", "failure_streak": 0})
    return 0


def proposal() -> int:
    """Run one policy-bounded proposal workflow and stop at the human approval gate."""
    state: RuntimeStateStore | None = None
    notifier: Notifier | None = None
    iteration_id: int | None = None
    budget: IterationBudget | None = None
    now_utc = datetime.now(UTC)
    try:
        config = load_config(ROOT)
        settings = load_runtime_policy_settings(ROOT)
        runtime_state = RuntimeStateStore(config.runtime.state_directory)
        workflow_state = StateStore(config.runtime.state_directory)
        state = runtime_state
        notifier = Notifier(settings.notifications)
        _emit_daily_report_if_due(state, notifier, settings=settings, now_utc=now_utc)

        waiting = workflow_state.latest_waiting()
        if waiting is not None:
            _print(_workflow_result(waiting))
            return 0

        local_date = local_now(settings, now_utc).date().isoformat()
        schedule = evaluate_schedule(
            settings,
            now_utc=now_utc,
            last_iteration_started_at=state.last_iteration_started_at(),
            iterations_today=state.iterations_started_on(local_date),
        )
        if not schedule.allowed:
            _print(
                {
                    "status": "skipped_schedule",
                    "reason": schedule.reason,
                    "detail": schedule.detail,
                }
            )
            return 0

        failure_stop = evaluate_stop_conditions(
            settings.stopping,
            consecutive_failures=state.consecutive_failed_iterations(),
        )
        if not failure_stop.allowed:
            _notify_once(
                state,
                notifier,
                event_key=f"autonomy-stop:{failure_stop.reason}",
                kind="autonomy_stopped",
                message="Autonomous work stopped by failure policy",
                payload={"reason": failure_stop.reason, "detail": failure_stop.detail},
                now_utc=now_utc,
            )
            _print(
                {
                    "status": "stopped",
                    "reason": failure_stop.reason,
                    "detail": failure_stop.detail,
                }
            )
            return 0

        decision = check_configurable_usage_budget(
            root=ROOT,
            executable=config.runtime.codex_executable,
        )
        if not decision.allowed:
            resets = ",".join(
                str(limit.resets_at) for limit in decision.limits if limit.resets_at is not None
            )
            event_suffix = resets or local_date
            _notify_once(
                state,
                notifier,
                event_key=f"usage-stop:{decision.reason}:{event_suffix}",
                kind="usage_limit_stop",
                message="Autonomous work stopped by Codex usage reserve",
                payload=decision.as_dict(),
                now_utc=now_utc,
            )
            _print(
                {
                    "status": "skipped_usage_guard",
                    "usage_guard": decision.as_dict(),
                }
            )
            return 0

        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            raise ValueError("GITHUB_TOKEN is required from an external secret provider")
        github = GitHubClient(config, token)
        errors = preflight_errors(ROOT, config, github)
        if errors:
            raise RuntimeError("; ".join(errors))

        repository_health = RepositoryHealthChecker(config, token).read(settings.stopping)
        repository_stop = evaluate_stop_conditions(
            settings.stopping,
            consecutive_failures=state.consecutive_failed_iterations(),
            repository_health=repository_health,
        )
        if not repository_stop.allowed:
            stop_key = f"repository-stop:{repository_stop.reason}:{repository_stop.detail}"
            _notify_once(
                state,
                notifier,
                event_key=stop_key,
                kind="autonomy_stopped",
                message="Autonomous work stopped by repository health policy",
                payload={
                    "reason": repository_stop.reason,
                    "detail": repository_stop.detail,
                },
                now_utc=now_utc,
            )
            _print(
                {
                    "status": "stopped",
                    "reason": repository_stop.reason,
                    "detail": repository_stop.detail,
                }
            )
            return 0

        budget = IterationBudget(settings.budget)
        budget.consume_task()
        iteration_id = state.start_iteration(local_date, now_utc)
        agent = BudgetedAgentRunner(
            CodexCliRunner(
                root=ROOT,
                executable=config.runtime.codex_executable,
                sandbox=config.runtime.codex_sandbox,
                web_search=config.runtime.codex_web_search,
            ),
            budget,
        )
        workflow = ProposalWorkflow(
            root=ROOT,
            config=config,
            state=workflow_state,
            agent=agent,
            github=github,
        )
        result = workflow.run()
        success = result.get("status") == "waiting_human"
        state.finish_iteration(
            iteration_id,
            status="success" if success else "failed",
            reason=str(result.get("status")),
            budget=budget.as_dict(),
        )
        iteration_id = None
        result["iteration_budget"] = budget.as_dict()
    except (RuntimeError, ValueError) as exc:
        if state is not None and iteration_id is not None:
            state.finish_iteration(
                iteration_id,
                status="failed",
                reason=str(exc),
                budget={} if budget is None else budget.as_dict(),
            )
        if state is not None and notifier is not None:
            if iteration_id is None:
                digest = hashlib.sha256(str(exc).encode("utf-8")).hexdigest()[:16]
                event_key = f"critical-error:preflight:{digest}"
            else:
                event_key = f"critical-error:iteration:{iteration_id}"
            _notify_once(
                state,
                notifier,
                event_key=event_key,
                kind="critical_error",
                message="Critical autonomous workflow error",
                payload={"error": str(exc)},
                now_utc=now_utc,
            )
        _print({"status": "failed", "error": str(exc)})
        return 1

    _print(result)
    return 0 if result.get("status") == "waiting_human" else 1


def main() -> int:
    """Parse the bounded orchestrator command set."""
    parser = argparse.ArgumentParser(description="AI First Learning local orchestrator")
    parser.add_argument("command", choices=("doctor", "usage", "policy", "resume", "proposal"))
    args = parser.parse_args()
    if args.command == "doctor":
        return doctor()
    if args.command == "usage":
        return usage()
    if args.command == "policy":
        return policy()
    if args.command == "resume":
        return resume()
    return proposal()


if __name__ == "__main__":
    sys.exit(main())
