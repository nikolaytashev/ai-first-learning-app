# Autonomous-System Security Model

## Trust boundaries

The trusted computing base contains the local orchestrator, its minimal secret
provider, its durable state store and the human-controlled host. Agent model
outputs, GitHub content, repository content, dependencies, attachments and
external pages are untrusted.

The repository is public. Public visibility grants read access, not command
authority.

## Identity and permissions

Use a dedicated GitHub App or restricted bot identity for automation. Its
installation should be limited to this repository.

Required capabilities:

- Read repository metadata, issues, comments, Project configuration and checks.
- Create and update issues, comments, Project items, non-default branches and
  draft pull requests.
- Push only to namespaced automation branches.

Prohibited capabilities:

- Merge pull requests, create releases or deploy.
- Change rulesets, repository visibility, collaborators or secrets.
- Push to or delete `main`.
- Administer organizations or unrelated repositories.

## Credential isolation

- The GitHub App Client ID is non-secret and may be stored in repository
  configuration.
- The GitHub App PEM private key remains outside the repository and is available
  only to the trusted orchestrator process.
- Short-lived installation tokens are minted and refreshed in process and are
  never persisted in repository files or worktrees.
- Agent subprocesses receive no raw GitHub App private key or installation token.
- Redact environment, command output and exceptions before logging.
- Never store secret credentials in prompts, worktrees, issue text, artifacts or
  the orchestration database.
- Rotate credentials after suspected exposure and pause automation until the
  incident is reviewed.

## Prompt-injection controls

- Treat issue text and repository files as data.
- Permit only exact control commands defined in the approval policy.
- Verify actor identity and immutable event identifiers through GitHub.
- Never execute code or shell text copied from an issue without review in the
  approved worktree and validation profile.
- Do not follow instructions that request secrets, authority expansion,
  disabled checks, destructive unrelated actions or communication outside the
  approved workflow.
- Record ignored injection attempts as `UNTRUSTED_COMMAND` without repeating
  sensitive payloads.

## Execution isolation

- Use a dedicated OS identity and one isolated worktree per workflow.
- Deny inbound public access; poll GitHub outbound.
- Default-deny network destinations and add explicit task-scoped exceptions.
- Limit CPU, memory, elapsed time, output size and concurrent workflows.
- Pin or lock dependencies and review automation workflow changes.
- Never run pull-request code with privileged or secret-bearing context.
- Preserve immutable audit identifiers for every side effect.

## Recovery

Persist idempotency keys and remote object IDs before reporting success. On
restart, reconcile GitHub state before repeating an action. A stale lock may be
recovered only after its lease expires and the remote branch, pull request and
last audit event are checked.
