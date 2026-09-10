from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"expected patch anchor not found in {path}: {old[:100]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_all(path: str, old: str, new: str, expected: int) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"expected {expected} anchors in {path}, found {count}")
    target.write_text(text.replace(old, new), encoding="utf-8")


# Model routing consumes the classification contract instead of documenting unused rules.
replace_once(
    "scripts/orchestrator/config.py",
    "    risk: str | None = None,\n) -> ModelSelection:\n",
    "    risk: str | None = None,\n    classification: Mapping[str, Any] | None = None,\n) -> ModelSelection:\n",
)
replace_once(
    "scripts/orchestrator/config.py",
    '''    allowed = cast(list[str], allowed_raw)\n    if profile_name not in allowed:\n        raise ValueError(f"profile {profile_name!r} is not allowed for role {role!r}")\n    if attempt >= 3:\n        current_index = allowed.index(profile_name)\n        if current_index + 1 < len(allowed):\n            profile_name = allowed[current_index + 1]\n\n    profile = _mapping(profiles.get(profile_name), f"profiles.{profile_name}")\n''',
    '''    allowed = cast(list[str], allowed_raw)\n    if profile_name not in allowed:\n        raise ValueError(f"profile {profile_name!r} is not allowed for role {role!r}")\n\n    profile_rank = {"text_light": 0, "code_light": 0, "balanced": 1, "deep": 2, "critical": 3}\n\n    def upgrade_once() -> None:\n        nonlocal profile_name\n        current_index = allowed.index(profile_name)\n        if current_index + 1 < len(allowed):\n            profile_name = allowed[current_index + 1]\n\n    def require_rank(minimum: int) -> None:\n        nonlocal profile_name\n        if profile_rank.get(profile_name, 0) >= minimum:\n            return\n        for candidate in allowed:\n            if profile_rank.get(candidate, 0) >= minimum:\n                profile_name = candidate\n                return\n        profile_name = allowed[-1]\n\n    classification = {} if classification is None else classification\n    if size == "L":\n        upgrade_once()\n    if classification.get("ambiguity") == "high":\n        upgrade_once()\n    if classification.get("architecture_change") is True:\n        require_rank(1)\n    if (\n        classification.get("security_sensitive") is True\n        or classification.get("concurrency_sensitive") is True\n    ):\n        require_rank(2)\n    if (\n        classification.get("destructive_migration") is True\n        or classification.get("data_loss_risk") is True\n    ):\n        require_rank(3)\n    previous_failures = classification.get("previous_failures")\n    if isinstance(previous_failures, int) and not isinstance(previous_failures, bool) and previous_failures >= 2:\n        upgrade_once()\n    if attempt >= 3:\n        upgrade_once()\n\n    profile = _mapping(profiles.get(profile_name), f"profiles.{profile_name}")\n''',
)

# The trusted context index stays in the runtime checkout; content may come from the fresh app snapshot.
replace_once(
    "scripts/orchestrator/control_plane.py",
    '''        settings: ControlPlaneSettings,\n        agent: AgentRunner,\n        github: GitHubClient,\n    ) -> None:\n        self._root = root\n        self._config = config\n        self._settings = settings\n        self._agent = agent\n        self._github = github\n        self._project: ProjectSnapshot | None = None\n''',
    '''        settings: ControlPlaneSettings,\n        agent: AgentRunner,\n        github: GitHubClient,\n        context_root: Path | None = None,\n    ) -> None:\n        self._root = root\n        self._context_root = root if context_root is None else context_root\n        self._config = config\n        self._settings = settings\n        self._agent = agent\n        self._github = github\n        self._project: ProjectSnapshot | None = None\n''',
)
replace_once(
    "scripts/orchestrator/control_plane.py",
    '''                "product_manager",\n                ["proposal_generation", "requirements", "planning", "discovery"],\n            )\n''',
    '''                "product_manager",\n                ["proposal_generation", "requirements", "planning", "discovery"],\n                content_root=self._context_root,\n            )\n''',
)
replace_once(
    "scripts/orchestrator/control_plane.py",
    '''                "business_analysis",\n                ["acceptance_criteria", "requirements", "planning", "proposal_generation"],\n            )\n''',
    '''                "business_analysis",\n                ["acceptance_criteria", "requirements", "planning", "proposal_generation"],\n                content_root=self._context_root,\n            )\n''',
)
replace_once(
    "scripts/orchestrator/control_plane.py",
    '''Human-created child issues may be superseded only with a clear reason. Dependencies must reference\ndesired child keys and must be acyclic. If PM classification is material/initial, approval_impact\nmust invalidate; uncertain -> decision_required; cancelled -> cancel. For non-material changes,\npreserve approval when the desired work remains within the approved scope.\n''',
    '''Human-created child issues may be superseded only with a clear reason. Dependencies must reference\ndesired child keys and must be acyclic. Every desired child must include the complete classification\nobject required by the schema and a specialists list. Mark learning_content true for learning-content\nauthoring/design. Request software_architect for architecture/security/data/concurrency-sensitive work\nand instructional_designer for learning-content work; the orchestrator deterministically enforces\nthese minimum specialist routes. If PM classification is material/initial, approval_impact must\ninvalidate; uncertain -> decision_required; cancelled -> cancel. For non-material changes, preserve\napproval when the desired work remains within the approved scope.\n''',
)

# Proposal generation can feed the live managed backlog instead of remaining a standalone legacy lane.
replace_once(
    "scripts/orchestrator/proposal.py",
    '''        state: StateStore,\n        agent: AgentRunner,\n        github: ProposalGitHub,\n    ) -> None:\n        self._root = root\n        self._config = config\n        self._state = state\n        self._agent = agent\n        self._github = github\n\n    def run(self) -> JsonObject:\n        """Generate, independently review, publish and then wait for a human."""\n        waiting = self._state.latest_waiting()\n        if waiting is not None:\n            return self._result(waiting)\n''',
    '''        state: StateStore,\n        agent: AgentRunner,\n        github: ProposalGitHub,\n        context_root: Path | None = None,\n        managed_issue: bool = False,\n    ) -> None:\n        self._root = root\n        self._context_root = root if context_root is None else context_root\n        self._config = config\n        self._state = state\n        self._agent = agent\n        self._github = github\n        self._managed_issue = managed_issue\n\n    def run(self, *, ignore_waiting: bool = False) -> JsonObject:\n        """Generate, independently review and publish one bounded Feature proposal."""\n        waiting = None if ignore_waiting else self._state.latest_waiting()\n        if waiting is not None:\n            return self._result(waiting)\n''',
)
replace_all(
    "scripts/orchestrator/proposal.py",
    '''                ["bootstrap", "proposal_generation", "discovery", "planning"],\n            )\n''',
    '''                ["bootstrap", "proposal_generation", "discovery", "planning"],\n                content_root=self._context_root,\n            )\n''',
    1,
)
replace_all(
    "scripts/orchestrator/proposal.py",
    '''                ["proposal_generation", "acceptance_criteria", "requirements", "planning"],\n            )\n''',
    '''                ["proposal_generation", "acceptance_criteria", "requirements", "planning"],\n                content_root=self._context_root,\n            )\n''',
    1,
)
replace_once(
    "scripts/orchestrator/proposal.py",
    '''        if issue is None:\n            issue = self._github.create_issue(\n                cast(str, proposal["title"]),\n                self._issue_body(workflow_id, proposal, marker),\n            )\n''',
    '''        if issue is None:\n            title = cast(str, proposal["title"])\n            if self._managed_issue and not title.startswith("[Feature]"):\n                title = f"[Feature] {title}"\n            issue = self._github.create_issue(\n                title,\n                self._issue_body(workflow_id, proposal, marker),\n            )\n''',
)
replace_once(
    "scripts/orchestrator/proposal.py",
    '''        self._github.update_project_fields(\n            project,\n            item_id,\n            {\n                "Status": "Awaiting Human",\n                "Product Approval": "Pending",\n                "Type": "Feature",\n                "Priority": cast(str, proposal["priority"]),\n                "Size": cast(str, proposal["size"]),\n                "Current Role": "Human",\n                "Automation State": "Waiting",\n                "Attempt Count": attempt_count,\n                "Workflow ID": workflow_id,\n            },\n        )\n''',
    '''        values: dict[str, str | int] = {\n            "Status": "Inbox" if self._managed_issue else "Awaiting Human",\n            "Product Approval": "Pending",\n            "Type": "Feature",\n            "Priority": cast(str, proposal["priority"]),\n            "Size": cast(str, proposal["size"]),\n            "Current Role": "PM" if self._managed_issue else "Human",\n            "Automation State": "Queued" if self._managed_issue else "Waiting",\n            "Attempt Count": attempt_count,\n            "Workflow ID": workflow_id,\n        }\n        if self._managed_issue:\n            values["Origin"] = "Agent"\n        self._github.update_project_fields(project, item_id, values)\n''',
)
replace_once(
    "scripts/orchestrator/proposal.py",
    '''        generated_note = (\n            "Generated autonomously. Product approval is pending; implementation is not authorized."\n        )\n        return "\\n".join(\n            [\n                marker,\n''',
    '''        generated_note = (\n            "Generated autonomously. Product approval is pending; implementation is not authorized."\n        )\n        managed_prefix: list[str] = []\n        if self._managed_issue:\n            proposal_id = str(proposal.get("proposal_id") or workflow_id)\n            metadata = {\n                "schema": 1,\n                "managed": True,\n                "origin": "Agent",\n                "type": "Feature",\n                "parent": None,\n                "key": f"proposal-{proposal_id.lower()}",\n                "revision": 0,\n                "approval": "pending",\n                "approval_digest": None,\n                "current_digest": None,\n                "last_human_comment_id": 0,\n                "paused": False,\n                "execution_state": "idle",\n                "risk": "medium",\n                "size": proposal.get("size") or "M",\n                "priority_override": None,\n            }\n            encoded = json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))\n            managed_prefix.append(f"<!-- orch-meta:{encoded} -->")\n        return "\\n".join(\n            [\n                *managed_prefix,\n                marker,\n''',
)

# Runtime uses a detached latest-origin/main application snapshot and autonomous backlog proposals.
replace_once(
    "scripts/run_orchestrator.py",
    '''from scripts.orchestrator.codex import CodexCliRunner\nfrom scripts.orchestrator.config import load_config\n''',
    '''from scripts.orchestrator.application_state import ApplicationStateManager\nfrom scripts.orchestrator.autonomous_control import AutonomousControlPlaneWorkflow\nfrom scripts.orchestrator.autonomous_implementation import AutonomousImplementationWorkflow\nfrom scripts.orchestrator.codex import CodexCliRunner\nfrom scripts.orchestrator.config import load_config\nfrom scripts.orchestrator.control_plane import parse_metadata\n''',
)
replace_once(
    "scripts/run_orchestrator.py",
    "from scripts.orchestrator.implementation import ImplementationWorkflow\n",
    "",
)
replace_once(
    "scripts/run_orchestrator.py",
    '''from scripts.orchestrator.safety_control import (\n    HardenedControlPlaneWorkflow,\n    run_safety_control,\n)\n''',
    '''from scripts.orchestrator.safety_control import run_safety_control\n''',
)
replace_once(
    "scripts/run_orchestrator.py",
    '''def _record_failed_iteration(\n''',
    '''def _has_open_managed_work(github: GitHubClient) -> bool:\n    for issue in github.list_issues(state="open"):\n        metadata = parse_metadata(issue.body)\n        if (\n            metadata is not None\n            and metadata.get("managed") is True\n            and metadata.get("type") in {"Epic", "Feature", "Task"}\n        ):\n            return True\n    return False\n\n\ndef _record_failed_iteration(\n''',
)
replace_once(
    "scripts/run_orchestrator.py",
    '''        budget = IterationBudget(settings.budget)\n        planning_agent = BudgetedAgentRunner(\n            CodexCliRunner(\n                root=ROOT,\n                executable=config.runtime.codex_executable,\n                sandbox=config.runtime.codex_sandbox,\n                web_search=config.runtime.codex_web_search,\n            ),\n            budget,\n        )\n        control = HardenedControlPlaneWorkflow(\n            root=ROOT,\n            config=config,\n            settings=control_settings,\n            agent=planning_agent,\n            github=github,\n        )\n''',
    '''        budget = IterationBudget(settings.budget)\n        application_state = ApplicationStateManager(\n            ROOT,\n            config.runtime.state_directory,\n            config.repository.default_branch,\n        )\n        application_snapshot = application_state.refresh()\n        planning_agent = BudgetedAgentRunner(\n            CodexCliRunner(\n                root=application_snapshot.root,\n                executable=config.runtime.codex_executable,\n                sandbox=config.runtime.codex_sandbox,\n                web_search=config.runtime.codex_web_search,\n            ),\n            budget,\n        )\n        control = AutonomousControlPlaneWorkflow(\n            root=ROOT,\n            config=config,\n            settings=control_settings,\n            agent=planning_agent,\n            github=github,\n            context_root=application_snapshot.root,\n        )\n''',
)
replace_once(
    "scripts/run_orchestrator.py",
    '''            implementation = ImplementationWorkflow(\n                root=ROOT,\n                config=config,\n                settings=implementation_settings,\n                github=github,\n                budget=budget,\n            )\n''',
    '''            implementation = AutonomousImplementationWorkflow(\n                root=ROOT,\n                config=config,\n                settings=implementation_settings,\n                github=github,\n                budget=budget,\n                application_state=application_state,\n            )\n''',
)
replace_once(
    "scripts/run_orchestrator.py",
    '''        pr_outcomes_reconciled = implementation_result.get("pr_outcomes_reconciled", 0)\n        feature_checks = implementation_result.get("feature_checks", 0)\n        worked = (\n''',
    '''        backlog_result: dict[str, object] = {"status": "not_needed"}\n        if (\n            repository_stop.allowed\n            and schedule.allowed\n            and implementation_result.get("status") == "idle"\n            and not _has_open_managed_work(github)\n        ):\n            budget.consume_task()\n            backlog_agent = BudgetedAgentRunner(\n                CodexCliRunner(\n                    root=application_snapshot.root,\n                    executable=config.runtime.codex_executable,\n                    sandbox=config.runtime.codex_sandbox,\n                    web_search=config.runtime.codex_web_search,\n                ),\n                budget,\n            )\n            backlog_result = cast(\n                dict[str, object],\n                ProposalWorkflow(\n                    root=ROOT,\n                    config=config,\n                    state=StateStore(config.runtime.state_directory),\n                    agent=backlog_agent,\n                    github=github,\n                    context_root=application_snapshot.root,\n                    managed_issue=True,\n                ).run(ignore_waiting=True),\n            )\n\n        pr_outcomes_reconciled = implementation_result.get("pr_outcomes_reconciled", 0)\n        feature_checks = implementation_result.get("feature_checks", 0)\n        worked = (\n''',
)
replace_once(
    "scripts/run_orchestrator.py",
    '''            or (isinstance(feature_checks, int) and feature_checks > 0)\n        )\n''',
    '''            or (isinstance(feature_checks, int) and feature_checks > 0)\n            or backlog_result.get("status") != "not_needed"\n        )\n''',
)
replace_once(
    "scripts/run_orchestrator.py",
    '''            "control_plane": control_result.as_dict(),\n            "implementation": implementation_result,\n            "iteration_budget": budget.as_dict(),\n''',
    '''            "control_plane": control_result.as_dict(),\n            "application_state": application_snapshot.as_dict(),\n            "implementation": implementation_result,\n            "backlog": backlog_result,\n            "iteration_budget": budget.as_dict(),\n''',
)

# BA schema-required classification is recorded by the specialized control-plane subclass.
# Add the missing model classification field to the documented required set.
replace_once(
    "config/model-profiles.yaml",
    '''    - data_loss_risk\n    - previous_failures\n''',
    '''    - data_loss_risk\n    - previous_failures\n    - learning_content\n''',
)

# Repository contracts know about the new trust/runtime surface.
replace_once(
    "scripts/validate_repository.py",
    '''    ".github/ISSUE_TEMPLATE/feature-proposal.yml",\n    ".github/PULL_REQUEST_TEMPLATE.md",\n''',
    '''    ".github/ISSUE_TEMPLATE/feature-proposal.yml",\n    ".github/PULL_REQUEST_TEMPLATE.md",\n    ".github/workflows/application-ci.yml",\n''',
)
replace_once(
    "scripts/validate_repository.py",
    '''    "schemas/agent-result.schema.json",\n    "schemas/feature-proposal.schema.json",\n''',
    '''    "schemas/agent-result.schema.json",\n    "schemas/feature-proposal.schema.json",\n    "schemas/specialist-guidance.schema.json",\n''',
)
replace_once(
    "scripts/validate_repository.py",
    '''    "scripts/orchestrator/__init__.py",\n    "scripts/orchestrator/codex.py",\n''',
    '''    "scripts/orchestrator/__init__.py",\n    "scripts/orchestrator/application_state.py",\n    "scripts/orchestrator/autonomous_control.py",\n    "scripts/orchestrator/autonomous_implementation.py",\n    "scripts/orchestrator/codex.py",\n''',
)

# Durable documentation of the manual-runtime / fresh-application-state boundary.
workflow = ROOT / "docs/autonomy/workflow.md"
text = workflow.read_text(encoding="utf-8")
anchor = "Usage reserve, per-iteration budget, repository health and failure-stop policies remain independent\nhard gates.\n"
addition = '''Usage reserve, per-iteration budget, repository health and failure-stop policies remain independent\nhard gates.\n\n### Trusted runtime versus application state\n\nThe local `main` checkout that contains orchestrator code/config is human-maintained. The running\norchestrator never checks out, resets, pulls or fast-forwards that trusted runtime tree. Before AI\nwork it fetches the default branch and maintains a detached read-only application snapshot under the\nstate directory. Planning agents and merged-Feature QA use that snapshot, while schemas, validation\npolicy and orchestration code continue to come from the manually updated trusted checkout.\n\nWhen the managed backlog is empty and autonomous cadence permits work, PM + BA may publish one\nagent-originated managed Feature proposal. The normal control plane then analyzes/decomposes it and\nstops at the same human Feature-approval boundary as human-originated work.\n\nTasks left in transient `running`/`review` state after a process or machine crash are reconciled on\nthe next run. An owned existing PR is recovered; otherwise the stable `agent/*` branch is requeued\nfor bounded rework without force-push.\n\nArchitecture/security/data/concurrency-sensitive Tasks are routed through Software Architect\nguidance before implementation. Learning-content Tasks are routed through Instructional Designer\nguidance. A specialist may constrain approved implementation, but any newly discovered human-owned\ndecision invalidates the parent approval and returns the Feature to the human gate.\n\nFeature completion QA runs against the latest fetched merged application commit and requires full\ndeterministic product validation before the independent QA role can close the Feature.\n'''
if anchor not in text:
    raise RuntimeError("workflow documentation anchor not found")
workflow.write_text(text.replace(anchor, addition, 1), encoding="utf-8")

# Focused regression/contract tests for routing and runtime composition.
(ROOT / "tests/test_autonomy_completion.py").write_text(
    '''from __future__ import annotations\n\nfrom pathlib import Path\n\nfrom scripts.orchestrator.config import load_config, select_model\n\n\nROOT = Path(__file__).resolve().parents[1]\n\n\ndef test_security_sensitive_small_task_uses_deep_implementer_profile() -> None:\n    config = load_config(ROOT)\n    model = select_model(\n        config,\n        "implementer",\n        "implementation",\n        1,\n        size="XS",\n        risk="medium",\n        classification={"security_sensitive": True},\n    )\n    assert model.profile == "deep"\n\n\ndef test_destructive_task_uses_critical_implementer_profile() -> None:\n    config = load_config(ROOT)\n    model = select_model(\n        config,\n        "implementer",\n        "implementation",\n        1,\n        size="S",\n        risk="medium",\n        classification={"destructive_migration": True},\n    )\n    assert model.profile == "critical"\n\n\ndef test_high_ambiguity_upgrades_small_implementer_once() -> None:\n    config = load_config(ROOT)\n    model = select_model(\n        config,\n        "implementer",\n        "implementation",\n        1,\n        size="XS",\n        risk="medium",\n        classification={"ambiguity": "high"},\n    )\n    assert model.profile == "balanced"\n\n\ndef test_runtime_composes_fresh_app_state_recovery_and_backlog_loop() -> None:\n    source = (ROOT / "scripts/run_orchestrator.py").read_text(encoding="utf-8")\n    implementation = (\n        ROOT / "scripts/orchestrator/autonomous_implementation.py"\n    ).read_text(encoding="utf-8")\n    assert "ApplicationStateManager" in source\n    assert "AutonomousControlPlaneWorkflow" in source\n    assert "AutonomousImplementationWorkflow" in source\n    assert "managed_issue=True" in source\n    assert "recover_interrupted_tasks()" in implementation\n    assert "Merged-product deterministic validation" in implementation\n    assert "software_architect" in implementation\n    assert "instructional_designer" in implementation\n''',
    encoding="utf-8",
)

print("autonomy completion patch applied")
