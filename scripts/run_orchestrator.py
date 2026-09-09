"""Command-line entry point for the local autonomous orchestrator."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from scripts.orchestrator.codex import CodexCliRunner
from scripts.orchestrator.config import load_config
from scripts.orchestrator.control_plane import ControlPlaneWorkflow
from scripts.orchestrator.github import GitHubClient
from scripts.orchestrator.implementation import ImplementationWorkflow
from scripts.orchestrator.notifications import Notifier
from scripts.orchestrator.proposal import ProposalWorkflow, preflight_errors
from scripts.orchestrator.repository_health import RepositoryHealthChecker
from scripts.orchestrator.runtime_config import (
    RuntimePolicySettings,
    load_control_plane_settings,
    load_implementation_settings,
    load_runtime_policy_settings,
)
from scripts.orchestrator.runtime_policy import (
    BudgetedAgentRunner,
    IterationBudget,
    daily_report_due,
    evaluate_schedule,
    evaluate_stop_conditions,
    local_now,
    schedule_interval_minutes,
)
from scripts.orchestrator.runtime_state import RuntimeStateStore
from scripts.orchestrator.state import StateStore, WorkflowState
from scripts.orchestrator.usage_guard import load_usage_guard_settings
from scripts.orchestrator.usage_policy import (
    check_configurable_usage_budget,
    load_usage_window_switches,
)

ROOT = Path(__file__).resolve().parents[1]


def _print(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True), flush=True)


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


def _trusted_github() -> tuple[object, RuntimePolicySettings, GitHubClient]:
    config = load_config(ROOT)
    settings = load_runtime_policy_settings(ROOT)
    load_control_plane_settings(ROOT)
    load_implementation_settings(ROOT)
    load_usage_guard_settings(ROOT)
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise ValueError("GITHUB_TOKEN is required from an external secret provider")
    github = GitHubClient(config, token)
    errors = preflight_errors(ROOT, config, github)
    if errors:
        raise RuntimeError("; ".join(errors))
    return config, settings, github


def doctor() -> int:
    """Verify all trusted local and GitHub preconditions without side effects."""
    try:
        config, _, github = _trusted_github()
        errors: list[str] = []
        project = github.project_snapshot()
        errors.extend(github.verify_project(project))
        errors.extend(github.verify_branch_rules())
        if config.authorization.command_prefix != load_control_plane_settings(ROOT).command_prefix:
            errors.append("GitHub and control-plane command prefixes do not match")
    except (RuntimeError, ValueError) as exc:
        errors = [str(exc)]

    result = {"status": "ready" if not errors else "blocked", "errors": errors}
    _print(result)
    return 0 if not errors else 1


def usage() -> int:
    """Show whether current Codex account usage permits a new agent workflow."""
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
    """Print resolved runtime, control-plane and implementation policy without starting work."""
    try:
        settings = load_runtime_policy_settings(ROOT)
        control = load_control_plane_settings(ROOT)
        implementation = load_implementation_settings(ROOT)
        usage_settings = load_usage_guard_settings(ROOT)
        usage_switches = load_usage_window_switches(ROOT)
    except ValueError as exc:
        _print({"status": "failed", "error": str(exc)})
        return 1
    _print(
        {
            "status": "ready",
            "autonomy": settings.as_dict(),
            "control_plane": {
                "poll_seconds": control.poll_seconds,
                "max_reconciliations_per_iteration": control.max_reconciliations_per_iteration,
                "auto_reconcile_human_comments": control.auto_reconcile_human_comments,
                "command_prefix": control.command_prefix,
            },
            "implementation": {
                "max_elapsed_seconds": implementation.max_elapsed_seconds,
                "max_corrective_cycles": implementation.max_corrective_cycles,
                "write_sandbox": implementation.write_sandbox,
            },
            "usage_guard": {
                "enabled": usage_settings.enabled,
                "five_hour_enabled": usage_switches.five_hour_enabled,
                "long_term_enabled": usage_switches.long_term_enabled,
            },
        }
    )
    return 0


def resume() -> int:
    """Clear the local consecutive-failure stop after a human has addressed the problem."""
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


def _iteration() -> tuple[int, dict[str, object]]:
    """Run one GitHub-control and, when cadence permits, one bounded implementation pass."""
    runtime_state: RuntimeStateStore | None = None
    notifier: Notifier | None = None
    budget: IterationBudget | None = None
    iteration_id: int | None = None
    now_utc = datetime.now(UTC)
    try:
        config, settings, github = _trusted_github()
        control_settings = load_control_plane_settings(ROOT)
        implementation_settings = load_implementation_settings(ROOT)
        runtime_state = RuntimeStateStore(config.runtime.state_directory)
        notifier = Notifier(settings.notifications)
        _emit_daily_report_if_due(
            runtime_state,
            notifier,
            settings=settings,
            now_utc=now_utc,
        )

        failure_stop = evaluate_stop_conditions(
            settings.stopping,
            consecutive_failures=runtime_state.consecutive_failed_iterations(),
        )
        if not failure_stop.allowed:
            _notify_once(
                runtime_state,
                notifier,
                event_key=f"autonomy-stop:{failure_stop.reason}",
                kind="autonomy_stopped",
                message="Autonomous work stopped by failure policy",
                payload={"reason": failure_stop.reason, "detail": failure_stop.detail},
                now_utc=now_utc,
            )
            return 0, {
                "status": "stopped",
                "reason": failure_stop.reason,
                "detail": failure_stop.detail,
            }

        usage_decision = check_configurable_usage_budget(
            root=ROOT,
            executable=config.runtime.codex_executable,
        )
        if not usage_decision.allowed:
            resets = ",".join(
                str(limit.resets_at)
                for limit in usage_decision.limits
                if limit.resets_at is not None
            )
            local_date = local_now(settings, now_utc).date().isoformat()
            _notify_once(
                runtime_state,
                notifier,
                event_key=f"usage-stop:{usage_decision.reason}:{resets or local_date}",
                kind="usage_limit_stop",
                message="Autonomous work stopped by Codex usage reserve",
                payload=usage_decision.as_dict(),
                now_utc=now_utc,
            )
            return 0, {
                "status": "skipped_usage_guard",
                "usage_guard": usage_decision.as_dict(),
            }

        budget = IterationBudget(settings.budget)
        planning_agent = BudgetedAgentRunner(
            CodexCliRunner(
                root=ROOT,
                executable=config.runtime.codex_executable,
                sandbox=config.runtime.codex_sandbox,
                web_search=config.runtime.codex_web_search,
            ),
            budget,
        )
        control = ControlPlaneWorkflow(
            root=ROOT,
            config=config,
            settings=control_settings,
            agent=planning_agent,
            github=github,
        )
        control_result = control.run_iteration()

        repository_health = RepositoryHealthChecker(
            config,
            os.environ.get("GITHUB_TOKEN", ""),
        ).read(settings.stopping)
        repository_stop = evaluate_stop_conditions(
            settings.stopping,
            consecutive_failures=runtime_state.consecutive_failed_iterations(),
            repository_health=repository_health,
        )

        schedule = evaluate_schedule(
            settings,
            now_utc=now_utc,
            last_iteration_started_at=runtime_state.last_iteration_started_at(),
            iterations_today=None,
        )
        implementation_result: dict[str, object]
        if not repository_stop.allowed:
            implementation_result = {
                "status": "stopped",
                "reason": repository_stop.reason,
                "detail": repository_stop.detail,
            }
        elif not schedule.allowed:
            implementation_result = {
                "status": "skipped_schedule",
                "reason": schedule.reason,
                "detail": schedule.detail,
                "current_interval_minutes": schedule_interval_minutes(
                    settings,
                    now_utc=now_utc,
                ),
            }
        else:
            implementation = ImplementationWorkflow(
                root=ROOT,
                config=config,
                settings=implementation_settings,
                github=github,
                budget=budget,
            )
            implementation_result = cast(
                dict[str, object],
                implementation.run_one_ready_task(),
            )

        worked = (
            control_result.reconciled > 0
            or control_result.commands > 0
            or implementation_result.get("status") not in {"idle", "skipped_schedule"}
            or int(implementation_result.get("pr_outcomes_reconciled", 0) or 0) > 0
            or int(implementation_result.get("feature_checks", 0) or 0) > 0
        )
        if worked:
            local_date = local_now(settings, now_utc).date().isoformat()
            iteration_id = runtime_state.start_iteration(local_date, now_utc)
            runtime_state.finish_iteration(
                iteration_id,
                status="success",
                reason=str(implementation_result.get("status") or "control_plane"),
                budget=budget.as_dict(),
            )
            iteration_id = None

        result: dict[str, object] = {
            "status": "completed" if worked else "idle",
            "control_plane": control_result.as_dict(),
            "implementation": implementation_result,
            "iteration_budget": budget.as_dict(),
            "current_interval_minutes": schedule_interval_minutes(settings, now_utc=now_utc),
        }
        return 0, result
    except (RuntimeError, ValueError) as exc:
        if runtime_state is not None and iteration_id is not None:
            runtime_state.finish_iteration(
                iteration_id,
                status="failed",
                reason=str(exc),
                budget={} if budget is None else budget.as_dict(),
            )
        if runtime_state is not None and notifier is not None:
            digest = hashlib.sha256(str(exc).encode("utf-8")).hexdigest()[:16]
            _notify_once(
                runtime_state,
                notifier,
                event_key=f"critical-error:{digest}",
                kind="critical_error",
                message="Critical autonomous workflow error",
                payload={"error": str(exc)},
                now_utc=now_utc,
            )
        return 1, {"status": "failed", "error": str(exc)}


def iteration() -> int:
    """Run exactly one GitHub-driven orchestration pass."""
    code, result = _iteration()
    _print(result)
    return code


def run_forever() -> int:
    """Poll GitHub continuously in the foreground until interrupted."""
    try:
        control = load_control_plane_settings(ROOT)
    except ValueError as exc:
        _print({"status": "failed", "error": str(exc)})
        return 1
    _print(
        {
            "status": "running",
            "mode": "github_control_plane",
            "poll_seconds": control.poll_seconds,
            "message": "GitHub Issues, comments and Project state are the command surface.",
        }
    )
    try:
        while True:
            _, result = _iteration()
            if result.get("status") != "idle":
                _print(result)
            time.sleep(control.poll_seconds)
    except KeyboardInterrupt:
        _print({"status": "stopped", "reason": "keyboard_interrupt"})
        return 0


def proposal() -> int:
    """Run the legacy autonomous proposal generator retained for compatibility."""
    state: RuntimeStateStore | None = None
    iteration_id: int | None = None
    budget: IterationBudget | None = None
    now_utc = datetime.now(UTC)
    try:
        config, settings, github = _trusted_github()
        runtime_state = RuntimeStateStore(config.runtime.state_directory)
        workflow_state = StateStore(config.runtime.state_directory)
        state = runtime_state
        waiting = workflow_state.latest_waiting()
        if waiting is not None:
            _print(_workflow_result(waiting))
            return 0
        decision = check_configurable_usage_budget(
            root=ROOT,
            executable=config.runtime.codex_executable,
        )
        if not decision.allowed:
            _print({"status": "skipped_usage_guard", "usage_guard": decision.as_dict()})
            return 0
        budget = IterationBudget(settings.budget)
        budget.consume_task()
        local_date = local_now(settings, now_utc).date().isoformat()
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
        result = ProposalWorkflow(
            root=ROOT,
            config=config,
            state=workflow_state,
            agent=agent,
            github=github,
        ).run()
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
        _print({"status": "failed", "error": str(exc)})
        return 1
    _print(result)
    return 0 if result.get("status") == "waiting_human" else 1


def main() -> int:
    """Parse the local bootstrap/runtime command set."""
    parser = argparse.ArgumentParser(description="AI First Learning local orchestrator")
    parser.add_argument(
        "command",
        choices=("doctor", "usage", "policy", "resume", "iteration", "run", "proposal"),
    )
    args = parser.parse_args()
    if args.command == "doctor":
        return doctor()
    if args.command == "usage":
        return usage()
    if args.command == "policy":
        return policy()
    if args.command == "resume":
        return resume()
    if args.command == "iteration":
        return iteration()
    if args.command == "run":
        return run_forever()
    return proposal()


if __name__ == "__main__":
    sys.exit(main())
