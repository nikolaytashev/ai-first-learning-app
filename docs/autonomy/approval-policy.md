# Human Approval Policy

## Authority

Only allow-listed GitHub users in `config/github.yaml` may issue authoritative orchestrator
commands or product-direction comments. Approval is valid only for the repository, canonical issue
and managed content revision recorded in the audit state.

The initial allow-listed human approver is `nikolaytashev`.

## GitHub command namespace

Commands must appear on their own line in an issue comment and use the `/orch` namespace:

| Command | Effect |
| --- | --- |
| `/orch analyze` | Refresh PM analysis for an Epic/Feature without implementation authority. |
| `/orch replan` | Run PM analysis and BA desired-state reconciliation for an Epic/Feature. |
| `/orch approve` | Approve the current managed Epic/Feature revision. Feature child Tasks may inherit the approval. |
| `/orch pause` | Prevent new autonomous steps for the item; the current atomic action may finish. |
| `/orch resume` | Resume a paused item if its current approval/dependencies permit it. |
| `/orch cancel <reason>` | Cancel/supersede the item without deleting audit history. |
| `/orch priority P0|P1|P2|P3` | Set a human priority override. |
| `/orch rework <reason>` | Return a Task to executable rework. |

The orchestrator rejects unknown commands, invalid arguments, edited commands whose audit state
cannot be verified, and commands issued by bots or non-allow-listed actors.

## Product comments and reconciliation

Normal comments from allow-listed humans on managed Epics/Features are product input. When automatic
comment reconciliation is enabled, new product comments cause PM/BA to recompute desired state.

PM classifies the change relative to the current managed specification:

- `non_material`: wording/clarification that does not change approved behaviour may preserve approval;
- `material`: scope, acceptance criteria, privacy/security/data/architecture constraints or other
  product behaviour changed, so previous approval is invalidated;
- `uncertain`: a human decision is missing or human comments conflict, so implementation waits;
- `cancelled`: explicit human product direction removes the item; open work is cancelled without
  hard deletion.

A material/uncertain change pauses affected child work and invalidates the Feature approval digest.
Implementation rechecks the current digest before validation and publication, so stale work cannot
be pushed or opened as a PR after requirements have changed.

## Approval integrity

- The approval record includes approver evidence, issue number, managed revision and a digest of
  approval-relevant content.
- A material change to scope, acceptance criteria, privacy, security, data model, architecture
  constraints or non-functional requirements invalidates approval.
- Label, assignee or Project-field changes alone do not create product approval.
- An agent cannot approve its own output by editing a Project field or issue body.
- Product approval does not authorize merge, release or deployment.
- Approval of one Feature does not authorize adjacent Features.
- Feature approval authorizes only bounded child Tasks whose parent/digest relationship is current.
- Epic approval does not implicitly approve child Features; each Feature keeps its own human product
  gate.

## Cancellation and historical work

Automation does not hard-delete GitHub issues. Obsolete work is closed as `not_planned` and Project
status becomes `Cancelled`. Completed/merged work remains historical evidence. If a later product
change must undo merged behaviour, the desired-state reconciliation creates new compensating work
instead of rewriting history.

## Required human gates

Human approval is always required for:

- Product scope, behaviour, priority overrides and success targets.
- Privacy, data ownership, security boundaries and public API commitments.
- Accepted architecture decisions with material operational impact.
- Destructive or irreversible data migrations.
- Budget and model policy changes.
- Repository permissions, rulesets and secrets.
- Pull-request merge, production deployment and release creation.
