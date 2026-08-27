# AI First Learning App

A mobile-first learning application for software professionals studying
artificial intelligence and core software-engineering topics.

## Initial product

The first pathway is AI Fundamentals for Software Engineers.

The initial release will include lessons, quizzes, answer explanations,
progress tracking, resume learning, reminders and limited offline access.

## Technology direction

- Flutter mobile application
- .NET backend
- PostgreSQL
- Python local multi-agent orchestrator
- GitHub Issues and Projects as the remote control plane
- Codex CLI as the initial agent execution provider

## Development model

Product proposals, priorities and approvals are managed through GitHub.

AI execution runs locally. Agents may create proposals and, after later workflow
implementation, code and reviews. The human owner approves product decisions,
merges pull requests and creates releases.

## Repository status

The repository contains the P0 autonomy contracts and the first executable local
orchestrator slice: the proposal workflow. It can run the Product Manager and
Business Analysis roles, validate their structured output, publish an idempotent
GitHub feature-proposal issue, add it to the configured GitHub Project, record
usage/audit evidence and stop for human approval.

The implementation workflow (approved issue -> worktree -> Implementer ->
validation -> QA -> Reviewer -> draft pull request) remains disabled until it is
implemented and independently validated.

Product behaviour marked `decision_required` must be resolved by the human
owner; agents may surface the decision but must not invent an answer.

Canonical project context starts at
[`docs/project-context/context-index.yaml`](docs/project-context/context-index.yaml).
The autonomous workflow and authority boundaries are documented under
[`docs/autonomy`](docs/autonomy). Local setup and execution are documented in
[`docs/autonomy/local-operation.md`](docs/autonomy/local-operation.md).

## Local validation

Use Python 3.12 or later:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.lock
python scripts/validate_repository.py
ruff check .
ruff format --check .
mypy scripts tests
pytest
```

The validation script checks YAML and JSON syntax, JSON Schema definitions,
context-index references, local Markdown links and required repository files.

## Bootstrap sequence

1. Configure the GitHub Project number/URL and required fields.
2. Provision the restricted GitHub App or bot identity outside the repository.
3. Apply the required no-bypass ruleset to `main`.
4. Install/authenticate Codex CLI on the local machine.
5. Inject the restricted GitHub credential from an external secret provider.
6. Run `python scripts/run_orchestrator.py doctor` until it reports `ready`.
7. Run `python scripts/run_orchestrator.py proposal`.
8. Review the generated GitHub proposal issue and approve or request changes as
   the human owner. No implementation starts from the proposal command.
