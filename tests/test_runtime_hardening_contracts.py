"""Regression contracts for autonomous runtime hardening."""

from __future__ import annotations

import inspect

from scripts import run_orchestrator
from scripts.orchestrator.safety_control import HardenedControlPlaneWorkflow


def test_safety_control_runs_before_failure_and_usage_gates() -> None:
    source = inspect.getsource(run_orchestrator._iteration)

    safety = source.index("run_safety_control(")
    failure_gate = source.index("evaluate_stop_conditions(")
    usage_gate = source.index("check_configurable_usage_budget(")

    assert safety < failure_gate < usage_gate


def test_normal_control_pass_uses_replay_aware_hardened_workflow() -> None:
    source = inspect.getsource(run_orchestrator._iteration)

    assert "HardenedControlPlaneWorkflow(" in source
    assert issubclass(HardenedControlPlaneWorkflow, object)


def test_runtime_failure_path_records_failure_before_returning_failed() -> None:
    source = inspect.getsource(run_orchestrator._iteration)
    exception_path = source[source.index("except (RuntimeError, ValueError) as exc:") :]

    assert "_record_failed_iteration(" in exception_path
    assert exception_path.index("_record_failed_iteration(") < exception_path.index(
        'return 1, {"status": "failed"'
    )


def test_iteration_and_continuous_run_hold_process_lock() -> None:
    iteration_source = inspect.getsource(run_orchestrator.iteration)
    run_source = inspect.getsource(run_orchestrator.run_forever)

    assert "orchestrator_process_lock(" in iteration_source
    assert "orchestrator_process_lock(" in run_source
