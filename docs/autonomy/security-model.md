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

The preferred GitHub App receives only:

- Contents: read/write;
- Issues: read/write;
- Pull requests: read/write;
- Checks: read-only;
- Metadata: read-only;
- Projects: read/write.

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

- The GitHub App Client ID is non-secret configuration.
- The GitHub App PEM private key is long-lived secret material and must be kept
  outside the repository with restrictive filesystem permissions.
- The trusted process uses the private key only to sign short-lived App JWTs and
  mint repository-scoped installation access tokens.
- Installation tokens are cached only in process memory and refreshed before
  expiry; they are never persisted.
- Autonomous Git pushes use the same restricted App token through a temporary
  `GIT_ASKPASS` helper, preventing fallback to the human owner's Git identity.
- Agent subprocesses receive neither the private key nor installation tokens.
- Redact environment, command output and exceptions before logging.
- Never store credentials in prompts, worktrees, issue text, artifacts or the
  orchestration database.
- Rotate the App private key after suspected exposure and pause automation until
  the incident is reviewed.

## Ruleset integrity without admin authority

The automation identity must not receive repository Administration permission
merely to inspect bypass configuration. The human owner verifies the no-bypass
ruleset, then commits its immutable ID and current `updated_at` fingerprint.
`doctor` verifies effective branch rules and fails if that fingerprint changes,
forcing a new human verification before autonomous execution can resume.

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
