# AI First Learning App

A mobile-first learning application for software professionals studying artificial intelligence
and core software-engineering topics.

## Initial product

The first pathway is AI Fundamentals for Software Engineers.

The initial release will include lessons, quizzes, answer explanations, progress tracking, resume
learning, reminders and limited offline access.

## Technology direction

- Flutter mobile application
- .NET backend
- PostgreSQL
- Python local multi-agent orchestrator
- GitHub Issues and Projects as the control plane
- Codex CLI as the initial agent execution provider

## Autonomous development model

After the local worker is started, normal product control happens in GitHub. GitHub Issues and
comments are the human-to-orchestrator interface, GitHub Project is the operational dashboard, and
pull requests are the human review/merge boundary.

The hierarchy is intentionally small:

```text
Epic (optional)
└── Feature
    ├── Task
    ├── Task
    └── Task
```

A human-created Epic or Feature issue is canonical; the agents do not replace it with a duplicate.
Product Management analyzes the current product intent and Business Analysis maintains the desired
child structure. Native GitHub sub-issues represent parent/child relationships and native issue
dependencies represent blocked-by ordering.

Pending/ready work may be reorganized when requirements change. In-progress work may be stopped or
superseded before publication. Issues are never hard-deleted by automation: obsolete work is closed
as not planned and retained for audit. Merged history is never rewritten; a changed requirement is
implemented through new compensating work when necessary.

A material Feature change invalidates its previous product approval. The orchestrator will not
publish implementation from a stale approval digest. Feature Tasks become executable only while the
parent Feature's current revision is approved. Epic approval does not implicitly approve its child
Features.

## Giving the orchestrator work in GitHub

Use **Issues → New issue → New feature** for a normal product capability or **New epic** for a
larger outcome that may require multiple Features. The issue form is deliberately lightweight: you
describe what you want and any important constraints; PM/BA agents produce the structured analysis,
acceptance criteria and decomposition.

Continue the product discussion in comments on that same Epic/Feature. Allow-listed human comments
are product input. When the meaning changes, PM classifies the change and BA reconciles the current
GitHub board against the new desired state. Tasks may therefore be created, updated, reprioritized,
reparented or cancelled as the Feature evolves.

Human-created work is recorded with Project field `Origin = Human`; agent-created child work uses
`Origin = Agent`. Managed issues also contain hidden orchestration metadata so hierarchy, revision,
approval and execution state can be recovered from GitHub even if local worker state is rebuilt.

## GitHub orchestrator commands

Commands are line-oriented comments and use the `/orch` namespace. Only allow-listed human users
may issue authoritative commands.

| Command | Valid on | Effect |
| --- | --- | --- |
| `/orch analyze` | Epic, Feature | Refresh PM analysis of the current issue/comments. It does not itself authorize implementation. |
| `/orch replan` | Epic, Feature | Run PM analysis plus BA desired-state reconciliation. Child work may be created, updated, reordered, reparented or cancelled without hard deletion. |
| `/orch approve` | Epic, Feature | Approve the current analyzed revision. On a Feature, bounded child Tasks inherit this approval and may become executable when dependencies are satisfied. On an Epic, child Features still require their own approval. |
| `/orch pause` | Epic, Feature, Task | Prevent new autonomous work for the item. A currently running atomic agent/tool action is allowed to finish, but stale scope is checked again before validation/push/PR publication. |
| `/orch resume` | Epic, Feature, Task | Resume an item after a human pause, subject to its current approval and dependencies. |
| `/orch cancel <reason>` | Epic, Feature, Task | Cancel/supersede the item and unnecessary open descendants using `not_planned`; no issue is hard-deleted. Completed/merged history is preserved. |
| `/orch priority P0` | Epic, Feature, Task | Set an explicit human priority override. Valid values are `P0`, `P1`, `P2`, `P3`. |
| `/orch rework <reason>` | Task | Return a Task to executable rework after human review or a closed/unmerged PR. |

Examples:

```text
Actually, offline quizzes should now be supported, but synchronization should happen only on Wi-Fi.
/orch replan
```

```text
/orch priority P0
```

```text
/orch cancel This capability is no longer part of the product direction.
```

A normal human comment can also trigger automatic reconciliation when
`control_plane.auto_reconcile_human_comments` is enabled. Use `/orch replan` when you want the intent
to be explicit and immediate in the audit trail.

## Task implementation lifecycle

One bounded Task is the implementation unit:

```text
Ready Task
→ isolated agent/* branch + git worktree
→ Implementer
→ deterministic repository validation
→ independent QA
→ independent Reviewer
→ bounded corrective cycles when required
→ push non-default branch
→ draft pull request
→ human merge
```

The orchestrator re-reads the Task and its parent Feature approval before implementation stages and
again before commit/push. A material requirement change therefore makes the work stale instead of
allowing old requirements to reach a PR.

Only the human owner merges pull requests. The orchestrator does not push to `main`, merge, deploy,
create releases, change rulesets or manage secrets.

After a Task PR is merged, the Task is completed. A Feature is completed only after all of its child
Tasks are completed and an independent Feature-level QA check passes against the high-level Feature
acceptance criteria.

## Runtime cadence and usage reserve

The worker is allowed to operate 24/7. There is no working-hours block and no daily iteration-count
cap. The default autonomous cadence is every 30 minutes. Between **23:00 and 07:00 Europe/Sofia** the
active cadence is every 15 minutes. GitHub is polled more frequently (currently every 60 seconds) so
new comments and commands can be discovered promptly.

Codex usage reserve remains a hard gate for agent work:

- 5-hour window: do not start below 60% remaining when that window is available;
- long-term weekly/monthly window: do not start below 40% remaining;
- missing optional 5-hour data alone does not block;
- unavailable required usage data fails closed.

Per-iteration AI/task/PR budgets and repository/failure stop conditions remain enforced independently
of the time-of-day cadence.

## Local orchestrator commands

These commands are machine/bootstrap controls; product commands belong in GitHub comments. Run `./orch init` once on a machine. After that the launcher restores local secrets, activates the virtual environment and installs updated locked dependencies automatically after restarts.

Running `./orch` with no arguments starts the continuous worker.

| Local command | Purpose |
| --- | --- |
| `./orch doctor` | Fail-closed verification of local checkout, Codex, GitHub identity, Project fields and `main` ruleset. No agent execution or GitHub mutation. |
| `./orch project-bootstrap` | Idempotently create missing Project custom fields and add missing single-select options from `config/github.yaml`. Existing fields/options are preserved; type mismatches fail closed. |
| `./orch usage` | Inspect the current Codex usage-reserve decision. |
| `./orch policy` | Print resolved cadence, control-plane, implementation and usage policy. |
| `./orch iteration` | Run one GitHub control-plane pass and, when cadence/safety gates permit, at most one bounded Task implementation pass. |
| `./orch run` | Start the foreground continuous worker. After this starts, normal commands and assignments are given in GitHub. Stop with Ctrl-C. |
| `./orch resume` | Clear a local consecutive-failure stop after the underlying problem has been addressed. This is distinct from `/orch resume` on a GitHub work item. |
| `./orch proposal` | Legacy autonomous proposal generator retained for compatibility. New product work should use the GitHub Epic/Feature issue forms instead. |

## Repository status

The repository contains the autonomous control contracts, GitHub intake/reconciliation workflow,
24/7 runtime policy and bounded Task delivery workflow. PM/BA outputs, implementation results and
independent QA/review outputs are schema validated. GitHub remains the durable control plane and
local SQLite state is used for runtime counters/idempotency rather than as the source of product
truth.

Product behaviour marked as requiring a decision must be resolved by the human owner; agents may
surface the decision but must not invent an answer.

Canonical project context starts at
[`docs/project-context/context-index.yaml`](docs/project-context/context-index.yaml). The autonomous
workflow and authority boundaries are documented under [`docs/autonomy`](docs/autonomy). Local setup
and execution details are in [`docs/autonomy/local-operation.md`](docs/autonomy/local-operation.md).

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

The validation script checks YAML/JSON syntax, JSON Schema definitions, context-index references,
local Markdown links, issue forms and required repository files.

## Bootstrap sequence

1. Configure the GitHub Project number and URL.
2. Run `./orch project-bootstrap` to reconcile the Project custom fields/options from `config/github.yaml`.
3. Create/install the repository-scoped GitHub App using `docs/autonomy/github-app-setup.md`.
4. Keep the active no-bypass `Protect main` ruleset with PR requirement, conversation resolution,
   deletion/force-push protection and required `repository-validation` check.
5. Install and authenticate Codex CLI on the local machine.
6. Run `./orch init` once. It copies the App PEM to gitignored `.local/github-app.pem`, stores the Project token in `.local/orchestrator.env`, applies restrictive filesystem permissions, and prepares `.venv`.
7. Run `./orch doctor` until it reports `ready`.
8. Optionally run `./orch iteration` for one controlled pass.
9. Start `./orch run` for continuous GitHub-controlled operation.
10. From then on, create Epic/Feature Issues and use their comments plus `/orch` commands to direct
    product work.

### User-owned GitHub Project authentication

The repository GitHub App remains the automation identity for repository, Issue, PR and Git
operations. GitHub currently does not allow an installation token to mutate a user-owned
Project V2. For `/users/.../projects/...`, `./orch init` stores a personal access token (classic) with only the `project` scope in gitignored `.local/orchestrator.env`. Do not grant `repo` scope. Organization-owned Projects continue to use the GitHub App token.

