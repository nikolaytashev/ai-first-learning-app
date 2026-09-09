# Local Orchestrator Operation

## Execution scope

The checked-in orchestrator supports a GitHub-driven control plane and bounded Task delivery:

- human-created canonical Epic/Feature intake;
- PM product analysis and change classification;
- BA desired-state decomposition/reconciliation;
- native GitHub sub-issue hierarchy and blocked-by dependencies;
- namespaced `/orch` commands and normal human-comment product input;
- material-change approval invalidation and stale-work prevention;
- one Task per isolated `agent/*` branch/worktree;
- Implementer, deterministic validation, independent QA and Reviewer;
- bounded corrective cycles and draft PR creation;
- human-only PR merge and Feature-level completion QA.

The worker never merges, deploys, releases, edits rulesets or manages secrets.

## Trusted prerequisites

Before autonomous execution, the human owner must configure:

- GitHub Project number and canonical URL;
- every Project field/option declared in `config/github.yaml`, including `Origin = Human|Agent`;
- repository-scoped GitHub App installation and its private key outside the repository;
- active no-bypass repository ruleset protecting `main`;
- local Codex CLI session authenticated through the approved provider;
- OpenSSL available to sign short-lived GitHub App JWTs.

The orchestrator verifies trusted GitHub/project/ruleset conditions with `doctor` and fails closed
when it cannot prove them.

## Automation identity

`GITHUB_AUTOMATION_IDENTITY_TYPE` must be one of:

- `github_app` — preferred. The trusted process signs a GitHub App JWT, resolves the installation
  for the configured repository, mints an installation access token and automatically refreshes it
  before expiration;
- `restricted_bot` — compatibility mode. `GITHUB_TOKEN` belongs to the configured dedicated bot
  account and its login exactly matches `GITHUB_AUTOMATION_LOGIN`.

For `github_app`, configure:

```text
GITHUB_APP_CLIENT_ID
GITHUB_APP_PRIVATE_KEY_PATH
GITHUB_APP_INSTALLATION_ID  # optional; repository installation is auto-discovered when omitted
```

The Client ID and installation ID are not secrets. The PEM private key is a long-lived credential:
it must live outside the repository, should be readable only by the orchestrator OS user, and must
never be forwarded to Codex. A private-key path resolving inside the repository is rejected.

Installation access tokens are cached in process memory and renewed automatically. They are never
written to disk. The same restricted GitHub App identity is used for REST/GraphQL operations and
for autonomous `git push`, so the worker does not silently fall back to the human owner's local Git
credentials.

## Required GitHub App permissions

Grant only the permissions required by the orchestrator:

Repository permissions:

- Contents: Read and write — read repository state and push `agent/*` branches;
- Issues: Read and write — issues, comments, sub-issues and issue dependencies;
- Pull requests: Read and write — create/update/close the orchestrator's draft PRs;
- Checks: Read-only — inspect `repository-validation` check runs;
- Metadata: Read-only — repository metadata, active branch rules and ruleset fingerprint.

Projects permission:

- Projects: Read and write — read/update Project V2 items and fields.

Do not grant Administration, Actions write, Deployments, Secrets, Environments, Members or other
unrelated write permissions. Install the App only on `nikolaytashev/ai-first-learning-app`.

## Ruleset verification without Administration permission

The App is intentionally not granted repository Administration permission. The human owner verifies
the no-bypass ruleset with owner access and checks its ID plus `updated_at` fingerprint into
`config/github.yaml`.

`doctor` still verifies the effective `main` branch rules through the rules API. It also reads the
pinned ruleset. Any later ruleset mutation changes `updated_at`, causing `doctor` to fail closed
until a human re-verifies the ruleset and updates the fingerprint. If the API exposes
`bypass_actors`, any non-empty bypass list is also rejected directly.

## Runtime environment

Non-secret identifiers may be configured in `config/github.yaml` or supplied as environment
overrides:

```text
GITHUB_PROJECT_NUMBER
GITHUB_PROJECT_URL
GITHUB_AUTOMATION_LOGIN
GITHUB_AUTOMATION_IDENTITY_TYPE
GITHUB_APP_CLIENT_ID
GITHUB_APP_INSTALLATION_ID
ORCHESTRATOR_STATE_DIRECTORY
```

`GITHUB_APP_PRIVATE_KEY_PATH` points to the external PEM file and should be supplied only to the
trusted orchestrator process. `GITHUB_TOKEN` is used only by the legacy `restricted_bot` mode.
Do not put raw tokens or private-key contents in `.env`, command-line arguments, prompts, logs or a
worktree.

The Codex child environment strips GitHub/provider secrets, token-like variables, password-like
variables and private-key material.

## Local bootstrap

Use Python 3.12 or later from a clean checkout of `main`:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.lock
python scripts/validate_repository.py
ruff check .
ruff format --check .
mypy scripts tests
pytest
openssl version
```

Install/authenticate Codex CLI separately.

## Preflight

Run:

```bash
python scripts/run_orchestrator.py doctor
```

`doctor` invokes no agent and mutates no GitHub state. It verifies:

- local checkout is clean `main`;
- Codex CLI is available;
- Project and automation identity configuration is present;
- the GitHub App can mint an installation token and is installed only for the configured repository;
- Project fields/options match the contract;
- active `main` rules require PRs, conversation resolution, `repository-validation`,
  non-fast-forward protection and deletion protection;
- the human-verified ruleset fingerprint is unchanged;
- GitHub and runtime command prefixes agree.

Resolve every blocked preflight result before starting continuous work.

## Inspecting safety policy

```bash
python scripts/run_orchestrator.py usage
python scripts/run_orchestrator.py policy
```

`usage` reads Codex account rate-limit state and applies configured reserve thresholds. `policy`
prints the 24/7 schedule, overnight active window, control-plane polling, implementation limits and
usage guard switches.

## One controlled pass

```bash
python scripts/run_orchestrator.py iteration
```

This performs one GitHub control-plane pass and, if cadence/usage/repository gates permit, at most
one bounded Task implementation pass. It is useful before enabling the persistent worker.

## Continuous GitHub-controlled operation

Start:

```bash
python scripts/run_orchestrator.py run
```

The process stays in the foreground until Ctrl-C. GitHub is polled every `control_plane.poll_seconds`
(currently 60 seconds). Normal product work is then assigned entirely in GitHub:

1. create a New Epic or New Feature issue;
2. discuss requirements in its comments;
3. use `/orch` commands documented in the repository README;
4. review/merge resulting draft PRs.

Autonomous implementation has no working-hours prohibition. Default cadence is 30 minutes; the
23:00–07:00 Europe/Sofia active window uses 15 minutes. There is no daily iteration-count cap.
Usage reserve, per-iteration resource caps and failure/repository stop conditions remain hard gates.

## Implementation publication safety

Task implementation runs in a separate git worktree with a write-enabled Codex sandbox. The agent
cannot push or create PRs. The deterministic orchestrator performs validation and independent QA /
review, then rechecks the Task and parent Feature approval digest before commit and again before
push. If the Feature changed materially while an atomic action was running, the Task becomes stale
and publication stops.

For push, the trusted process requests a current installation token and supplies it to Git only via
a short-lived `GIT_ASKPASS` helper stored in the ignored orchestrator state directory. The token is
not embedded in the remote URL or command line; the helper is deleted immediately after the push.

## Restart and recovery behaviour

GitHub is the durable product/control-plane source of truth. Managed issues contain hidden metadata
for origin, hierarchy, revision, approval digest and execution state. Local `.orchestrator` SQLite
state stores iteration/failure/notification counters and legacy proposal idempotency data.

After restart the worker re-reads GitHub state, reconciles task dependencies and observes existing
draft PR outcomes. A merged orchestrator PR completes its Task; a closed/unmerged PR returns the
Task to rework. Cancelled managed work is closed as not planned rather than deleted.

## Legacy proposal command

`python scripts/run_orchestrator.py proposal` remains available for compatibility with the original
single-proposal bootstrap workflow. New product work should use the GitHub Epic/Feature Issue Forms
and `/orch` command surface instead.
