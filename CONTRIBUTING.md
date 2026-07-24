# Contributing

## Before starting

Product features, bugs and architecture changes require a GitHub issue with
clear acceptance criteria. Autonomous implementation additionally requires the
issue's Product Approval field to be `Approved`.

Repository-control and bootstrap changes explicitly requested by the human owner
may be prepared before the first autonomous issue exists, but they still require
a feature branch and pull-request review.

## Workflow

1. Branch from `master` using `feature/`, `fix/`, `docs/` or `agent/`.
2. Keep the change focused on one approved issue or bootstrap objective.
3. Add or update tests and documentation with the implementation.
4. Run the commands under **Local validation** in `README.md`.
5. Open a draft pull request using the repository template.
6. Resolve required checks and review conversations.
7. Let the human owner merge the pull request.

Do not commit secrets, generated build output or local orchestrator state.

## Product ambiguity

Create a `Decision required` issue when a choice changes user-visible
behaviour, privacy, security, data ownership, acceptance criteria or product
scope. Implementation must wait for the human-owned decision.
