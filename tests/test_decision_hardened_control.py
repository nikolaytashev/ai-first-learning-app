"""Regression coverage for Decision handling in the hardened control plane."""

from __future__ import annotations

import inspect

from scripts.orchestrator.safety_control import HardenedControlPlaneWorkflow


def test_hardened_control_delegates_decisions_before_parent_analysis() -> None:
    """Decision `/orch ask` must use the base read-only path, never PM work-item analysis."""
    source = inspect.getsource(HardenedControlPlaneWorkflow._process)

    decision_guard = source.index('if artifact_type == "Decision":')
    decision_delegate = source.index("return super()._process(managed)")
    task_guard = source.index('if artifact_type == "Task":')
    parent_analysis = source.index("should_analyze =")

    assert decision_guard < decision_delegate < task_guard < parent_analysis
