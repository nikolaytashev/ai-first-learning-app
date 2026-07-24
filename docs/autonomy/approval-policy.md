# Human Approval Policy

## Authority

Only allow-listed GitHub users in `config/github.yaml` may issue control
commands. Approval is valid only for the repository, issue and content revision
recorded in the audit event.

The initial allow-listed human approver is `nikolaytashev`.

## Commands

Commands must appear on their own line in an issue or pull-request comment:

| Command | Effect |
| --- | --- |
| `/approve` | Approve the current proposal revision for implementation |
| `/request-changes <reason>` | Return the item for product or requirements revision |
| `/pause` | Prevent the worker from starting new steps |
| `/resume` | Resume a paused workflow if its approval is still valid |
| `/cancel <reason>` | Move the workflow to `Cancelled` |

The orchestrator must reject unknown commands, edited commands whose audit state
cannot be verified and commands issued by bots or non-allow-listed actors.

## Approval integrity

- The approval record includes approver, comment ID, time, issue number,
  proposal version and a digest of approval-relevant content.
- A material change to scope, acceptance criteria, privacy, security, data
  model, architecture constraints or non-functional requirements invalidates
  the approval.
- Label, assignee or Project-field changes alone do not create approval.
- An agent cannot approve its own output by editing a Project field.
- Product approval does not authorize merge, release or deployment.
- Approval of one issue does not authorize adjacent work.

## Required human gates

Human approval is always required for:

- Product scope, behaviour, priority and success targets.
- Privacy, data ownership, security boundaries and public API commitments.
- Accepted architecture decisions with material operational impact.
- Destructive or irreversible data migrations.
- Budget and model policy changes.
- Repository permissions, rulesets and secrets.
- Pull-request merge, production deployment and release creation.
