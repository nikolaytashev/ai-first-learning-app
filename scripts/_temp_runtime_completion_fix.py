from pathlib import Path

path = Path("scripts/orchestrator/implementation.py")
text = path.read_text(encoding="utf-8")

replacements = [
    (
        '''self._audit(feature.number, f"Feature integration validation failed on origin/main `{app_sha}`:\n{findings}")''',
        '''self._audit(
                    feature.number,
                    (
                        f"Feature integration validation failed on origin/main `{app_sha}`:\\n"
                        f"{findings}"
                    ),
                )''',
    ),
    (
        '''"Recovered interrupted workflow; unpublished work will be safely regenerated on the existing agent branch."''',
        '''(
                        "Recovered interrupted workflow; unpublished work will be safely "
                        "regenerated on the existing agent branch."
                    )''',
    ),
    (
        '''"Define implementation constraints and technical boundaries. Do not approve human-owned "
                    "architecture decisions; return decision_required when such a decision is missing."''',
        '''"Define implementation constraints and technical boundaries. "
                    "Do not approve human-owned architecture decisions; return decision_required "
                    "when such a decision is missing."''',
    ),
    (
        '''"Define learning-design requirements for objectives, sequencing, exercises and assessment. "
                    "Do not invent unresolved product or technical facts."''',
        '''"Define learning-design requirements for objectives, sequencing, exercises and "
                    "assessment. Do not invent unresolved product or technical facts."''',
    ),
    (
        '''f"Feature integration validation failed on origin/main `{app_sha}`:\\n{findings}",''',
        '''(
                        f"Feature integration validation failed on origin/main `{app_sha}`:\\n"
                        f"{findings}"
                    ),''',
    ),
    (
        '''    def _validate_current_application_state(self, feature_number: int) -> tuple[ValidationRun, str]:
        """Validate the latest remote application state without updating the orchestrator checkout."""''',
        '''    def _validate_current_application_state(
        self, feature_number: int
    ) -> tuple[ValidationRun, str]:
        """Validate latest remote app state without moving the orchestrator checkout."""''',
    ),
    (
        '''            pr = None
            pr_number = metadata.get("pr_number")''',
        '''            recovered_pr = None
            pr_number = metadata.get("pr_number")''',
    ),
    (
        '''                    pr = candidate
            if pr is None and isinstance(branch, str) and branch:''',
        '''                    recovered_pr = candidate
            if recovered_pr is None and isinstance(branch, str) and branch:''',
    ),
    (
        '''                    pr = candidate
            if pr is not None and pr.state == "open":
                metadata["execution_state"] = "awaiting_merge"
                metadata["pr_number"] = pr.number''',
        '''                    recovered_pr = candidate
            if recovered_pr is not None and recovered_pr.state == "open":
                metadata["execution_state"] = "awaiting_merge"
                metadata["pr_number"] = recovered_pr.number''',
    ),
    (
        '''self._audit(task.number, f"Recovered interrupted workflow from existing PR #{pr.number}.")''',
        '''self._audit(
                    task.number,
                    f"Recovered interrupted workflow from existing PR #{recovered_pr.number}.",
                )''',
    ),
    (
        '''            context = render_context(select_context_documents(self._root, role, task_types))''',
        '''            context_role = "architect" if role == "software_architect" else role
            context = render_context(
                select_context_documents(worktree, context_role, task_types)
            )''',
    ),
]

for old, new in replacements:
    if old in text:
        text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")

# Let the backlog proposal store retire a human-gated proposal after its managed Feature closes.
state_path = Path("scripts/orchestrator/state.py")
state = state_path.read_text(encoding="utf-8")
anchor = '''    def mark_blocked(self, workflow_id: str) -> None:
        """Stop a workflow without publishing side effects."""
        self._set_status(workflow_id, "blocked")

'''
replacement = anchor + '''    def mark_completed(self, workflow_id: str) -> None:
        """Retire a published proposal after its managed Feature has completed or closed."""
        self._set_status(workflow_id, "completed")

'''
if "def mark_completed(" not in state:
    if anchor not in state:
        raise SystemExit("StateStore mark_blocked anchor not found")
    state = state.replace(anchor, replacement, 1)
state_path.write_text(state, encoding="utf-8")

backlog_path = Path("scripts/orchestrator/backlog.py")
backlog = backlog_path.read_text(encoding="utf-8")
old = '''        return {"status": "closed_waiting", "issue_number": issue_number}
    return ProposalWorkflow'''
new = '''        state.mark_completed(waiting.workflow_id)
    return ProposalWorkflow'''
if old not in backlog:
    raise SystemExit("backlog closed-waiting anchor not found")
backlog_path.write_text(backlog.replace(old, new, 1), encoding="utf-8")
