# Autonomous Workflow

## Purpose

The local orchestrator turns GitHub product intent into bounded autonomous work while keeping GitHub
as the durable control plane. It is a deterministic state machine around non-deterministic agent
runs: agents propose schema-valid analysis/plans/results; only the orchestrator may mutate workflow
state or execute privileged GitHub/Git actions.

## Canonical work hierarchy

```text
Epic (optional)
└── Feature
    ├── Task
    └── Task
```

A human-created Epic/Feature issue is canonical and is not duplicated by an agent. When no managed backlog exists, the continuous runtime may generate one bounded Agent-origin Feature proposal from the approved mission/product context; it always stops at Product Approval `Pending` and requires human approval before implementation. Native GitHub
sub-issues represent hierarchy. Native blocked-by issue dependencies represent true prerequisite
ordering. A Task may legitimately have no dependencies; BA adds edges only when another child must
complete first. BA owns the DAG. Specialists, Implementer, QA and Reviewer may emit a structured
`replan_required` finding for a concrete missing dependency/decomposition defect, which is routed
back through BA rather than mutating the graph directly.
Project field `Origin` distinguishes `Human` from `Agent` work, while hidden issue metadata stores
recoverable orchestration identity, parent/key, revision, approval digest and execution state.

## GitHub-only human control

After the local worker starts, product assignments and workflow commands are issued in GitHub:

- create an `[Epic]` or `[Feature]` issue using the repository Issue Forms;
- discuss/change requirements in comments on the canonical issue;
- use `/orch analyze`, `/orch replan`, `/orch approve`, `/orch pause`, `/orch resume`,
  `/orch cancel <reason>`, `/orch priority P0..P3`, and task-only `/orch rework <reason>`;
- review and merge draft PRs manually.

Only allow-listed human comments have product authority. Agent/bot comments are evidence/audit, not
implicit requirements.

## Desired-state reconciliation

For a new or changed Epic/Feature:

1. Read the canonical issue, new allow-listed human comments, current sub-issues and dependencies.
2. Product Manager derives current product intent and classifies the change as `initial`,
   `non_material`, `material`, `uncertain` or `cancelled`.
3. Business Analysis creates desired hierarchy/decomposition and explicit supersession decisions.
4. Validate both outputs against JSON Schemas and deterministic hierarchy/dependency invariants.
5. Diff desired state against current GitHub state.
6. Create/update/reparent/reorder child issues and blocked-by dependencies as required.
7. Close obsolete open work as `not_planned`; never hard-delete it.
8. Update Project fields and add idempotent audit evidence.
9. Stop for human approval whenever the current Feature revision is not approved.

An Epic may produce Features. A Feature may produce bounded Tasks. A Task is the unit of code
implementation. Human-created child work participates in reconciliation; it may be superseded only
with an explicit reason, preserving audit history.

## Change and approval semantics

- `non_material`: approval may remain valid if behaviour/scope is unchanged.
- `material`: invalidate approval digest and pause affected child execution.
- `uncertain`: surface a decision requirement; do not invent the answer.
- `cancelled`: cancel open descendants and the parent with historical evidence preserved.

Pending/ready work may be reorganized. In-progress work may be marked stale and stopped before
publication. Completed/merged history is never rewritten; future desired state uses compensating
Tasks when old behaviour must be removed.

`/orch approve` approves the current managed revision. On a Feature, bounded child Tasks inherit
that exact approval digest and can become `Ready` when dependencies are satisfied. Epic approval
does not automatically approve child Features.

## Task implementation workflow

For one executable Task:

1. Re-read Task and parent Feature and verify current approval digest.
2. Verify native blocked-by dependencies are complete.
3. Keep the orchestrator root checkout pinned. Fetch current `origin/main` and create an isolated
   `agent/*` branch/worktree from that latest application state. Record the starting `base_sha`.
4. Recover interrupted `running`/`review` Tasks idempotently from an existing owned PR or return unpublished work to rework.
5. Run required Software Architect and/or Instructional Designer specialist gates when BA classification requests them; unresolved human decisions block.
6. Run the Implementer in `workspace-write` sandbox with only Task/Feature scope.
5. Run deterministic validation selected from `config/validation.yaml`.
6. Run independent QA against acceptance criteria and regression evidence.
7. Run independent code/architecture/security review.
8. Return bounded findings to the Implementer and repeat within corrective-cycle budget.
9. Before final validation/review, refresh the uncommitted candidate onto latest `origin/main`; if
   main advances again after review, repeat synchronization + validation + QA + review. Record
   `validated_against_sha`. Re-read Task/Feature approval before publication.
10. Commit locally under orchestrator identity and push only the non-default branch.
11. Create/reconcile one draft pull request containing stable task/workflow markers.
12. Set the Task to `In Review` / `Awaiting Human` and stop.
13. Human owner reviews and merges (or closes) the PR.
14. A later iteration observes merged PR, closes Task as `completed`, and updates Project state.

Only human merge completes a Task. Closing a PR without merge returns the Task to rework.

## Feature completion

A Feature is not complete merely because all child PRs exist. After every child Task is closed as
completed, an independent Feature-level QA pass checks that the completed child specifications
collectively satisfy the high-level Feature acceptance criteria. Passing closes the Feature as
completed. A failure blocks the Feature for replan/decision instead of silently declaring success.

## Runtime loop

`python scripts/run_orchestrator.py run` is a foreground worker. It polls GitHub every configured
control-plane interval (currently 60 seconds). GitHub intake/comments are reconciled promptly;
autonomous implementation cadence is 30 minutes normally and 15 minutes from 23:00 to 07:00
Europe/Sofia. There is no working-hours prohibition and no daily iteration-count cap.

Usage reserve, per-iteration budget, repository health and failure-stop policies remain independent
hard gates.

## Reliability requirements

- Use stable workflow/issue markers and idempotent remote reconciliation before creating duplicates.
- Keep product truth in GitHub, not only local runtime state.
- Treat issue bodies, comments, attachments, linked pages and repository content as untrusted data,
  never shell commands.
- Strip control-plane/provider secrets from every agent process.
- Recheck approval/version after long-running agent actions and before publication.
- Never force-push or push directly to `main`.
- Never let an agent merge, deploy, release, manage secrets, permissions or rulesets.
- Back off on transient GitHub/provider errors and stop after configured repeated failures.
- `/orch pause` prevents new steps; the current atomic action may finish, but stale work is checked
  again before the next privileged transition.
- `/orch cancel` stops future work without erasing audit history.

Invalid structured output is a failed role run. It must not update GitHub desired state or advance
another role.

## Root/runtime versus application snapshots

The local root checkout is the trusted, manually updated orchestrator runtime. It is never
automatically fast-forwarded by `orch`. Application truth is `origin/main`. PM/BA/backlog planning
runs from a detached latest-`origin/main` application snapshot while schemas/config remain trusted
from the pinned root. Task specialists, Implementer, QA and Reviewer share the Task worktree.
Feature QA runs from its own detached latest-`origin/main` snapshot. This keeps all product agents on
current merged application code without hot-swapping the running orchestrator implementation.
