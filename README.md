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

AI execution runs locally. Agents may create code and reviews, but the human
owner approves product decisions, merges pull requests and creates releases.

## Repository status

The repository currently contains the P0 contracts and controls required before
the local autonomous orchestrator is implemented. Product behaviour marked
`decision_required` must be resolved by the human owner; agents may create
decision issues but must not invent an answer.

Canonical project context starts at
[`docs/project-context/context-index.yaml`](docs/project-context/context-index.yaml).
The autonomous workflow and authority boundaries are documented under
[`docs/autonomy`](docs/autonomy).

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

1. Resolve the blocking settings listed in
   [`docs/autonomy/budgets.md`](docs/autonomy/budgets.md) and
   [`config/github.yaml`](config/github.yaml).
2. Apply the required GitHub Project fields and protect `master`.
3. Provision the restricted GitHub App or bot identity and configure its
   credentials outside the repository.
4. Implement the local Python orchestrator against the committed schemas.
5. Run [`mission.yaml`](mission.yaml), which may create proposals but must stop
   before implementation until the human owner approves them.
