# Repository Agent Instructions

## Authority

Agents may:

- Analyse requirements.
- Propose features and implementation plans.
- Modify files inside an assigned Git worktree.
- Add and update tests.
- Produce structured QA and review reports.

Agents may not:

- Push directly to `main`.
- Merge pull requests.
- Create releases.
- Change repository visibility.
- Access or modify secrets.
- Weaken security controls.
- Deploy to production.
- Change product scope without human approval.

## Product ambiguity

Any uncertainty affecting user-visible behaviour, privacy, security, data
ownership or acceptance criteria must be returned to the Product Manager or
human owner.

Agents must not silently invent product behaviour.

## Development workflow

All implementation work must be associated with an approved GitHub issue.

The Python orchestrator is responsible for running required formatting,
building, testing, linting and validation commands.

An agent may inspect or run a focused diagnostic command, but the final
validation suite must be executed independently by the orchestrator.

## Corrective handoffs

When work cannot be completed, the agent must return:

- Outcome status.
- Responsible role.
- Reason code.
- Explanation.
- Required actions.
- Supporting evidence.
- Affected acceptance criteria.

Typical routes include:

- QA defect → Implementer.
- Review finding → Implementer.
- Missing architecture decision → Architect.
- Product ambiguity → Product Manager.
- Human-owned decision → Human owner.
- Oversized issue → Issue Planner.

## Changeability

Design and implementation must isolate expected variation points:

- AI provider integrations.
- GitHub or work-management integrations.
- Workflow definitions.
- Approval policies.
- Agent roles.
- Validation profiles.
- Persistence.
- Execution logging.

Avoid speculative abstraction. Add an abstraction only when it protects a
known or reasonably expected variation point.

## Auditability

Every agent action must record:

- Agent identity and version.
- Action type.
- Start and completion time.
- Elapsed time.
- Token usage.
- Parent workflow.
- GitHub issue or pull request.
- Outcome.
- Response or structured handoff.
