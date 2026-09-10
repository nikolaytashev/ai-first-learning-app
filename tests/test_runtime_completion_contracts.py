import json
from pathlib import Path

from scripts.orchestrator.validation import run_validation

ROOT = Path(__file__).resolve().parents[1]


def test_specialist_schema_and_backlog_runtime_exist() -> None:
    assert (ROOT / "schemas/specialist-review.schema.json").is_file()
    backlog = (ROOT / "scripts/orchestrator/backlog.py").read_text(encoding="utf-8")
    proposal = (ROOT / "scripts/orchestrator/proposal.py").read_text(encoding="utf-8")
    state = (ROOT / "scripts/orchestrator/state.py").read_text(encoding="utf-8")
    assert "has_active_managed_backlog" in backlog
    assert "ProposalWorkflow" in backlog
    assert "completed_features" in backlog
    assert "supplemental_context=delivered_context" in backlog
    assert "Supplemental delivered-product history" in proposal
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
    assert "_sync_uncommitted_work_with_main" in implementation
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


def test_dependency_replan_and_latest_app_snapshot_contracts() -> None:
    specialist_schema = json.loads(
        (ROOT / "schemas/specialist-review.schema.json").read_text(encoding="utf-8")
    )
    implementation_schema = json.loads(
        (ROOT / "schemas/implementation-result.schema.json").read_text(encoding="utf-8")
    )
    review_schema = json.loads(
        (ROOT / "schemas/agent-review.schema.json").read_text(encoding="utf-8")
    )
    assert "replan_required" in specialist_schema["properties"]["verdict"]["enum"]
    assert "replan_required" in implementation_schema["properties"]["status"]["enum"]
    assert "replan_required" in review_schema["properties"]["verdict"]["enum"]

    implementation = (ROOT / "scripts/orchestrator/implementation.py").read_text(encoding="utf-8")
    control = (ROOT / "scripts/orchestrator/control_plane.py").read_text(encoding="utf-8")
    runtime = (ROOT / "scripts/run_orchestrator.py").read_text(encoding="utf-8")
    assert "_task_graph_context" in implementation
    assert "_request_parent_replan" in implementation
    assert 'metadata["base_sha"]' in implementation
    assert 'metadata["validated_against_sha"]' in implementation
    assert "_sync_uncommitted_work_with_main" in implementation
    assert '"agent_replan_requests": []' in control
    assert "_complete_agent_replan" in control
    assert "application_root=planning_snapshot.path" in runtime
    assert "context_root=backlog_snapshot.path" in runtime


def test_application_snapshot_helper_never_moves_root_branch() -> None:
    snapshot = (ROOT / "scripts/orchestrator/application_snapshot.py").read_text(encoding="utf-8")
    assert '"worktree", "add", "--detach"' in snapshot
    assert '"fetch", "origin", default_branch' in snapshot
    assert '"checkout"' not in snapshot
    assert '"pull"' not in snapshot
