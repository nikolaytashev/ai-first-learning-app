from pathlib import Path

from scripts.orchestrator.validation import run_validation

ROOT = Path(__file__).resolve().parents[1]


def test_specialist_schema_and_backlog_runtime_exist() -> None:
    assert (ROOT / "schemas/specialist-review.schema.json").is_file()
    backlog = (ROOT / "scripts/orchestrator/backlog.py").read_text(encoding="utf-8")
    state = (ROOT / "scripts/orchestrator/state.py").read_text(encoding="utf-8")
    assert "has_active_managed_backlog" in backlog
    assert "ProposalWorkflow" in backlog
    assert "completed_features" in backlog
    assert "supplemental_context=delivered_context" in backlog
    assert "state.mark_completed(waiting.workflow_id)" in backlog
    assert "def mark_completed(" in state


def test_runtime_integrates_recovery_specialists_and_backlog() -> None:
    implementation = (ROOT / "scripts/orchestrator/implementation.py").read_text(encoding="utf-8")
    runtime = (ROOT / "scripts/run_orchestrator.py").read_text(encoding="utf-8")
    assert "recover_interrupted_tasks" in implementation
    assert "_run_specialists" in implementation
    assert '"rebase"' in implementation
    assert "workflow_id: str" in implementation
    assert "agent/task-{task.number}-{slug}-{attempt}" in implementation
    assert "_validate_current_application_state" in implementation
    assert "generate_next_feature_if_empty" in runtime


def test_integration_validation_can_skip_candidate_guardrail_check(tmp_path: Path) -> None:
    policy = tmp_path / "policy"
    execution = tmp_path / "execution"
    (policy / "config").mkdir(parents=True)
    execution.mkdir()
    (policy / "config/validation.yaml").write_text(
        "profiles: {}\nselection:\n  always_run: []\n  include_matching_profiles: false\n",
        encoding="utf-8",
    )
    result = run_validation(
        execution,
        ["config/runtime-generated-example.yaml"],
        policy_root=policy,
        enforce_guardrails=False,
    )
    assert result.status == "passed"
