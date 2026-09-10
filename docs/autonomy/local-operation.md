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
- restricted automation identity and external credential provider;
- active no-bypass repository ruleset protecting `main`;
- local Codex CLI session authenticated through the approved provider.

The orchestrator verifies trusted GitHub/project/ruleset conditions with `doctor` and fails closed
when it cannot prove them.

## Automation identity

`GITHUB_AUTOMATION_IDENTITY_TYPE` must be one of:

- `github_app` — the checked-in non-secret Client ID plus an external PEM private key are used to
  mint and refresh short-lived repository-scoped installation tokens;
- `restricted_bot` — `GITHUB_TOKEN` belongs to the configured dedicated bot account and its login
  exactly matches `GITHUB_AUTOMATION_LOGIN`.

A GitHub App is preferred for long-lived automation because installation can be repository-scoped
and installation access tokens are short-lived. The trusted worker creates and refreshes those
tokens automatically. Raw credentials must never be tracked by Git. Machine-local credentials may be stored only under the gitignored `.local/` directory with restrictive filesystem permissions and are never forwarded to Codex.

The identity needs issue/comment/Project/sub-issue/dependency and draft-PR write permissions plus
repository/rules read access. It must not have merge, release, deployment, secret, ruleset,
collaborator or visibility-management authority.

## Runtime environment

Non-secret identifiers may be configured in `config/github.yaml` or supplied as environment
overrides. The GitHub App Client ID is checked into `config/github.yaml` and normally needs no local
override.

The only required local GitHub App credential setting is:

```text
GITHUB_APP_PRIVATE_KEY_PATH
```

Optional overrides include:

```text
GITHUB_PROJECT_NUMBER
GITHUB_PROJECT_URL
GITHUB_AUTOMATION_LOGIN
GITHUB_AUTOMATION_IDENTITY_TYPE
GITHUB_APP_CLIENT_ID
GITHUB_APP_INSTALLATION_ID
ORCHESTRATOR_STATE_DIRECTORY
```

The canonical launcher stores the PEM at gitignored `.local/github-app.pem` with mode 600. `GITHUB_APP_INSTALLATION_ID` is optional because the worker can discover the App installation from the configured repository.

For a user-owned Project, `./orch init` also stores `GITHUB_PROJECT_TOKEN` in gitignored `.local/orchestrator.env` with mode 600. The token must be a classic PAT with only the `project` scope.

For legacy `restricted_bot`, `GITHUB_TOKEN` is secret and must be injected by an external secret
provider/environment. Do not put it in `.env`, command-line arguments, prompts, logs or the
worktree.

The Codex child environment strips GitHub/provider secrets, token-like variables, password-like
variables and private-key material.

## Local bootstrap

Use Python 3.12 or later from a clean checkout of `main`. The preferred one-time setup is:

```bash
./orch init
```

It securely prompts for the Project token and the existing GitHub App PEM path, copies secrets into
`.local/`, fixes permissions and creates/updates `.venv`. The `.local/` directory is gitignored.

Manual validation remains available:

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

Install/authenticate Codex CLI separately.

## Preflight

Run:

```bash
./orch doctor
```

`doctor` invokes no agent and mutates no GitHub state. It verifies:

- local checkout is clean `main`;
- Codex CLI is available;
- Project and automation identity configuration is present;
- restricted GitHub credential matches its configured identity mode;
- Project fields/options match the contract;
- active `main` rules require PRs, conversation resolution, `repository-validation`,
  non-fast-forward protection and deletion protection;
- the human-verified ruleset fingerprint has not changed and no bypass actors are present;
- GitHub and runtime command prefixes agree.

Resolve every blocked preflight result before starting continuous work.

## Inspecting safety policy

```bash
./orch usage
./orch policy
```

`usage` reads Codex account rate-limit state and applies configured reserve thresholds. `policy`
prints the 24/7 schedule, overnight active window, control-plane polling, implementation limits and
usage guard switches.

## One controlled pass

```bash
./orch iteration
```

This performs one GitHub control-plane pass and, if cadence/usage/repository gates permit, at most
one bounded Task implementation pass. It is useful before enabling the persistent worker.

## Continuous GitHub-controlled operation

Start:

```bash
./orch run
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

Git push uses the same short-lived GitHub App installation token as the API control plane. The token
is supplied to git through a temporary `GIT_ASKPASS` helper, not a remote URL or command argument,
and the helper is deleted immediately after the push. Personal local Git credentials are not used
for autonomous publication.

## Restart and recovery behaviour

After a machine restart, no exports or virtual-environment activation are needed. From the repository root, `./orch` starts the continuous worker and `./orch <command>` runs any local control command. The launcher reloads `.local/orchestrator.env`, supplies the App PEM path and refreshes locked Python dependencies when needed.


GitHub is the durable product/control-plane source of truth. Managed issues contain hidden metadata
for origin, hierarchy, revision, approval digest and execution state. Local `.orchestrator` SQLite
state stores iteration/failure/notification counters and legacy proposal idempotency data.

After restart the worker re-reads GitHub state, reconciles task dependencies and observes existing
draft PR outcomes. A merged orchestrator PR completes its Task; a closed/unmerged PR returns the
Task to rework. Cancelled managed work is closed as not planned rather than deleted.

## Legacy proposal command

`./orch proposal` remains available for compatibility with the original
single-proposal bootstrap workflow. New product work should use the GitHub Epic/Feature Issue Forms
and `/orch` command surface instead.
