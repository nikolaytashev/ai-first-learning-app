# Autonomous Workflow

## Purpose

The local orchestrator converts approved GitHub state into bounded agent work.
It is a deterministic state machine around non-deterministic agent runs. Agents
may propose outputs; only the orchestrator may advance workflow state after
validating schemas, authority and evidence.

## Control-plane events

The orchestrator polls GitHub outbound. It accepts an event only when:

- The repository matches `config/github.yaml`.
- The event has not already been processed.
- The actor and command satisfy `approval-policy.md`.
- The issue is not cancelled, blocked or already owned by another workflow.
- The event's issue version still matches the approval.

Issue bodies, comments, attachments and linked pages are otherwise untrusted
data and never become shell commands.

## States and transitions

| Current state | Required input | Next state | Owner |
| --- | --- | --- | --- |
| Inbox | Valid proposal or decision request | Awaiting Human | Product Manager or Business Analyst |
| Awaiting Human | Valid `/approve` by allow-listed owner | Ready | Human owner |
| Awaiting Human | `/request-changes` | Inbox | Human owner |
| Ready | Lock acquired and budgets available | In Progress | Orchestrator |
| In Progress | Plan and implementation complete | In Review | Implementer |
| In Review | QA failure with retry remaining | In Progress | QA |
| In Review | QA pass and review requested | In Review | Reviewer |
| In Review | Review failure with retry remaining | In Progress | Reviewer |
| In Review | QA and review pass | Awaiting Human | Orchestrator |
| Awaiting Human | Draft pull request merged by human | Done | Human owner |
| Any active state | Retry exhausted or required decision missing | Blocked | Orchestrator |
| Any non-terminal state | Valid `/cancel` | Cancelled | Human owner |

The GitHub Project `Status` is the user-facing state. `Automation State` tracks
the worker state: `Queued`, `Running`, `Waiting`, `Failed` or `Completed`.

## Proposal workflow

1. Load the context index and the documents selected for discovery.
2. Run the Product Manager to generate outcome-oriented proposals.
3. Run the Business Analyst to remove duplicates, split oversized work,
   identify missing decisions and make acceptance criteria testable.
4. Validate each proposal against `schemas/feature-proposal.schema.json`.
5. Create or update idempotent GitHub issues and add them to the configured
   Project.
6. Set Product Approval to `Pending`, Automation State to `Waiting` and Current
   Role to `Human`.
7. Add an audit comment and stop.

Proposal generation does not authorize implementation.

## Implementation workflow

1. Re-read the approved issue and verify that its approved content digest has
   not changed.
2. Acquire a repository-and-issue lock.
3. Load task-specific context.
4. Produce an implementation plan and validate its scope.
5. Create an isolated feature branch and worktree.
6. Run the Implementer.
7. Run the independent validation profile selected from changed paths.
8. Run independent QA against every acceptance criterion.
9. Run independent code and architecture review.
10. Apply bounded corrective handoffs when allowed.
11. Re-run the full required validation suite.
12. Push the non-default branch and open a draft pull request.
13. Record evidence, set Current Role to `Human` and stop.

Only the human owner merges.

## Reliability requirements

- Use one durable workflow ID and one idempotency key per external action.
- Persist state before and after every side effect.
- Acquire a lease before running an issue; renew it with the heartbeat.
- Recover expired leases after verifying remote state.
- Deduplicate issues, comments, branches and pull requests after restarts.
- Back off on GitHub rate limits and transient failures.
- Publish heartbeat time, current workflow and last failure without secrets.
- `/pause` prevents new work and lets the current atomic action finish.
- `/cancel` stops future steps; it does not erase audit history.

Invalid structured output is a failed role run. It must not update GitHub state
or start another role.
