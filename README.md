# AI First Learning App

> Mobile-first, free-first learning app for IT professionals. The first pathway is AI Fundamentals for Software Engineers.

## Product direction

The initial product deliberately avoids AI-consuming end-user features so the first release can remain free without ads or recurring AI inference cost. The primary client is Flutter; web presentation/landing surfaces can be added separately later.

## Autonomous development

This repository is prepared for a local, GitHub-controlled multi-agent development workflow. GitHub Issues/Projects are the durable human control plane. The local orchestrator uses Codex CLI as the initial execution provider and preserves human authority over product approval, pull-request merge and release decisions.

### Work hierarchy

The preferred hierarchy is:

```text
Epic (optional)
└── Feature
    ├── Task
    ├── Task
    └── Task
```

A human-created Epic or Feature Issue is canonical; the orchestrator does not create a duplicate wrapper. Child work uses native GitHub sub-issues and native blocked-by dependencies where applicable.

### Roles

- PM — product intent, outcome, priority and feature-level acceptance criteria.
- BA — refinement, decomposition, desired-state reconciliation and backlog reorganization.
- Architect — architecture decisions when required.
- Instructional Designer — learning structure when content design requires it.
- Implementer — one bounded approved Task at a time.
- QA — independent verification.
- Reviewer — independent code/solution review.
- Human owner — product authority, Feature approval, PR merge and release authority.

### GitHub command surface

Human product commands are issued as Issue comments:

```text
/orch analyze
/orch replan
/orch approve
/orch pause
/orch resume
/orch cancel <reason>
/orch priority P0
/orch rework <reason>
```

`/orch rework` applies to Tasks. Product requirement comments can also trigger reconciliation when material changes are detected.

### Approval and publication safety

Human approval applies to the current Feature revision. Child Tasks within approved scope inherit that approval. A material human requirement change invalidates approval, pauses affected autonomous publication and causes PM/BA reconciliation before work resumes.

The orchestrator re-reads the Task and its parent Feature approval before implementation stages and again before commit/push. A material requirement change therefore makes the work stale instead of allowing old requirements to reach a PR.

Only the human owner merges pull requests. The orchestrator does not push to `main`, merge, deploy, create releases, change rulesets or manage secrets.

After a Task PR is merged, the Task is completed. A Feature is completed only after all of its child Tasks are completed and an independent Feature-level QA check passes against the high-level Feature acceptance criteria.

## Runtime cadence and usage reserve

The worker is allowed to operate 24/7. There is no working-hours block and no daily iteration-count cap. The default autonomous cadence is every 30 minutes. Between **23:00 and 07:00 Europe/Sofia** the active cadence is every 15 minutes. GitHub is polled more frequently (currently every 60 seconds) so new comments and commands can be discovered promptly.

Codex usage reserve remains a hard gate for agent work:

- 5-hour window: do not start below 60% remaining when that window is available;
- long-term weekly/monthly window: do not start below 40% remaining;
- missing optional 5-hour data alone does not block;
- unavailable required usage data fails closed.

Per-iteration AI/task/PR budgets and repository/failure stop conditions remain enforced independently of the time-of-day cadence.

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

The repository contains the autonomous control contracts, GitHub intake/reconciliation workflow, 24/7 runtime policy and bounded Task delivery workflow. PM/BA outputs, implementation results and independent QA/review outputs are schema validated. GitHub remains the durable control plane and local SQLite state is used for runtime counters/idempotency rather than as the source of product truth.

Product behaviour marked as requiring a decision must be resolved by the human owner; agents may surface the decision but must not invent an answer.

Canonical project context starts at [`docs/project-context/context-index.yaml`](docs/project-context/context-index.yaml). The autonomous workflow and authority boundaries are documented under [`docs/autonomy`](docs/autonomy). Local setup and execution details are in [`docs/autonomy/local-operation.md`](docs/autonomy/local-operation.md).

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

The validation script checks YAML/JSON syntax, JSON Schema definitions, context-index references, local Markdown links, issue forms and required repository files.

## Bootstrap sequence

1. Configure the GitHub Project number and URL.
2. Run `./orch project-bootstrap` to reconcile the Project custom fields/options from `config/github.yaml`.
3. Create/install the repository-scoped GitHub App using `docs/autonomy/github-app-setup.md`.
4. Keep the active no-bypass `Protect main` ruleset with PR requirement, conversation resolution, deletion/force-push protection and required `repository-validation` check.
5. Install and authenticate Codex CLI on the local machine.
6. Run `./orch init` once. It copies the App PEM to gitignored `.local/github-app.pem`, stores the Project token in `.local/orchestrator.env`, applies restrictive filesystem permissions, and prepares `.venv`.
7. Run `./orch doctor` until it reports `ready`.
8. Optionally run `./orch iteration` for one controlled pass.
9. Start `./orch run` (or simply `./orch`) for continuous GitHub-controlled operation.
10. From then on, create Epic/Feature Issues and use their comments plus `/orch` commands to direct product work.

### User-owned GitHub Project authentication

The repository GitHub App remains the automation identity for repository, Issue, PR and Git operations. GitHub currently does not allow an installation token to mutate a user-owned Project V2. For `/users/.../projects/...`, `./orch init` stores a personal access token (classic) with only the `project` scope in gitignored `.local/orchestrator.env`. Do not grant `repo` scope. Organization-owned Projects continue to use the GitHub App token.
