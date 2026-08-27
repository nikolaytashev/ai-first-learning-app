# Local Orchestrator Operation

## Current execution scope

The checked-in orchestrator implements the bootstrap **proposal workflow only**.
It may run the Product Manager and Business Analysis roles, validate their
structured output, create an idempotent GitHub feature-proposal issue, attach it
to the configured GitHub Project, publish audit evidence and stop at the human
approval gate.

It does not implement an approved issue. Worktree creation, implementation, QA,
review, corrective cycles and draft pull-request creation remain disabled until
the implementation workflow is added and independently validated.

## Trusted prerequisites

Before autonomous proposal execution, the human owner must configure:

- The GitHub Project number and canonical URL.
- Every Project field and option declared in `config/github.yaml`.
- A restricted automation identity and its external credential provider.
- An active repository ruleset protecting `main` with no bypass actors.
- A local Codex CLI session authenticated through the approved provider.

The orchestrator verifies these conditions at runtime and fails closed when it
cannot prove them.

## Automation identity

`GITHUB_AUTOMATION_IDENTITY_TYPE` must be one of:

- `github_app` — `GITHUB_TOKEN` is a GitHub App installation access token. The
  installation token must expose exactly this repository and no others. The
  configured automation login is retained as the expected identity label for
  audit/configuration; repository scope is verified from GitHub before work.
- `restricted_bot` — `GITHUB_TOKEN` belongs to the configured dedicated bot
  account. The authenticated GitHub login must exactly match
  `GITHUB_AUTOMATION_LOGIN`.

A GitHub App is preferred for long-lived automation because its installation can
be repository-scoped and its installation access tokens are short-lived. Token
creation and refresh belong to the external secret provider; raw credentials
must never be stored in this repository or exposed to Codex subprocesses.

The automation identity needs only the permissions required by
`config/github.yaml`. Reading active branch rules also requires read access to
repository administration metadata. Do not grant ruleset write, merge, release,
deployment, secret-management, collaborator-management or visibility-management
permissions.

## Runtime environment

The non-secret identifiers may be configured in `config/github.yaml` or supplied
as environment overrides:

```text
GITHUB_PROJECT_NUMBER
GITHUB_PROJECT_URL
GITHUB_AUTOMATION_LOGIN
GITHUB_AUTOMATION_IDENTITY_TYPE
ORCHESTRATOR_STATE_DIRECTORY
```

`GITHUB_TOKEN` is secret and must be injected by the external secret provider.
Do not put it in `.env`, command-line arguments, prompts, logs or the Git
worktree.

## Local bootstrap

Use Python 3.12 or later. Run from a clean checkout of `main`:

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

Install Codex CLI separately and authenticate it before running the worker.
The orchestrator never forwards GitHub credentials, API keys, private-key
material, token-like variables or password-like variables into the Codex child
environment.

## Preflight

Run:

```bash
python scripts/run_orchestrator.py doctor
```

`doctor` does not invoke an agent and does not mutate GitHub. It verifies:

- Local checkout is `main` and clean.
- Codex CLI is available.
- Required project and identity configuration is present.
- The supplied restricted GitHub credential is valid for its configured mode.
- The GitHub Project exists and its required fields/options match the contract.
- Active `main` rules require pull requests, conversation resolution,
  `repository-validation`, non-fast-forward updates and deletion protection.
- The active repository ruleset contains no bypass actors.

A blocked result must be resolved before running a proposal.

## First autonomous proposal

When `doctor` reports `ready`, run:

```bash
python scripts/run_orchestrator.py proposal
```

The worker then:

1. Runs deterministic repository validation.
2. Loads only task-scoped documents from the canonical context index.
3. Routes Product Manager and Business Analysis through the approved model
   profiles.
4. Requires JSON-Schema-valid output and deterministic workflow/proposal
   identity checks.
5. Applies bounded retries, one bounded PM revision cycle, elapsed-time limits
   and token warnings.
6. Persists workflow state, role telemetry and idempotency reservations in the
   local SQLite state store before GitHub side effects.
7. Reconciles or creates the proposal issue and Project item.
8. Sets Product Approval to `Pending`, Current Role to `Human` and Automation
   State to `Waiting`.
9. Publishes a model/attempt/token audit comment.
10. Stops with `waiting_human`.

No implementation starts from this command.

## Restart behaviour

The default state directory is `.orchestrator`, which is ignored by Git. The
SQLite store records durable workflow IDs, schema-valid PM/BA outputs, measured
usage and idempotency keys. If the process stops after reserving a GitHub side
effect, a later invocation reconciles the marker/project state before creating
a duplicate.

If a completed proposal is already waiting for human action, another `proposal`
invocation returns the waiting workflow instead of generating a second issue.
