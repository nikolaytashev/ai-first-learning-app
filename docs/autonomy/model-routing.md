# Model Routing and Reasoning Policy

## Objective

Use the least expensive model profile that can reliably complete the assigned
role action. Model strength does not expand an agent's authority, scope or
permissions.

The authoritative machine-readable configuration is
[`config/model-profiles.yaml`](../../config/model-profiles.yaml).

## Selection process

Before every agent action, the orchestrator classifies the task using:

- Role and action type.
- Issue size.
- Risk.
- Ambiguity.
- Affected areas.
- Security sensitivity.
- Persistence and migration impact.
- Architecture impact.
- Concurrency or synchronization complexity.
- Data-loss risk.
- Previous failures.

The orchestrator then:

1. Starts from the role's default or action-specific profile.
2. Applies size and risk overrides.
3. Applies minimum profiles required by security or architecture risk.
4. Verifies that the selected profile is allowed for the role.
5. Records the classification, selected profile and routing reasons.
6. Checks the remaining usage and retry budget before execution.

A model must not select its own model profile.

## Profiles

| Profile | Model | Effort | Use |
| --- | --- | --- | --- |
| `text_light` | `gpt-5.6-luna` | Low | Classification, metadata and non-material documentation changes |
| `code_light` | `gpt-5.4-mini` | Medium | Small scoped code, tests and routine QA |
| `balanced` | `gpt-5.6-terra` | Medium | Normal product, requirements, content and implementation work |
| `deep` | `gpt-5.6-sol` | High | Architecture, complex implementation and independent review |
| `critical` | `gpt-5.6-sol` | Extra high | Security, destructive migration, data-loss and difficult concurrency risks |

## Role defaults

### Product Manager

Use `balanced` for feature proposals, scope definition, product alternatives and
priority recommendations. Use `text_light` only for classification or a
non-material revision. Escalate to `deep` for conflicting product goals or
complex product trade-offs.

The Product Manager must stop rather than escalate when a human-owned product
decision is missing.

### Business Analyst

Use `balanced` for requirements analysis, acceptance criteria, traceability and
issue decomposition. Use `text_light` for mechanical documentation
synchronization, context-index maintenance and issue metadata. Use `deep` for
conflicting authoritative sources or complex cross-component decomposition.

### Software Architect

Use `deep` by default for architecture, boundaries, non-functional requirements
and significant trade-offs. Use `balanced` when applying an already accepted
pattern within one component. Use `critical` only for security boundaries,
destructive migrations, data-loss risks, concurrency or a justified failed
`deep` attempt.

### Instructional Designer

Use `balanced` for lesson specifications, module design, learning objectives and
assessment strategy. Use `text_light` for metadata or approved-template
application. Use `deep` for pathway design or complex curriculum consistency.

### Implementer

Select by issue size:

- `XS` and `S`: `code_light`.
- `M`: `balanced`.
- `L`: `deep`, after the Business Analyst confirms that further decomposition
  would reduce coherence or increase risk.

Risk overrides size. High risk requires at least `deep`. Critical risk may use
`critical` only when an activation condition in the configuration is present.

### QA

Use `code_light` for small, well-defined changes and analysis of deterministic
test evidence. Use `balanced` for normal behavioural validation and
multi-component acceptance criteria. Use `deep` for security, data consistency,
offline synchronization or difficult intermittent behaviour.

Python executes the deterministic validation commands. QA interprets evidence
and verifies behaviour; it does not consume model usage to run standard test
suites.

### Reviewer

Use `balanced` for XS and S low-risk diffs. Use `deep` for normal application
code, persistent state, APIs, orchestration and cross-component changes. Use
`critical` only for security, destructive migration, data-loss, concurrency or
repeated-review failure.

## Escalation

Escalation requires all of:

- A stable reason code.
- New evidence showing why the current profile was insufficient.
- Remaining action and workflow budget.
- An allowed target profile.
- A fresh or focused prompt appropriate to the failure.

The normal sequence is:

1. First failure: retry the same profile with a focused evidence packet.
2. Same root cause again: move up one allowed profile.
3. Third agent failure: start a fresh session at the role's allowed maximum.
4. Fourth agent failure: stop and request human intervention.

Do not repeat the same prompt without new evidence.

## Stop conditions

More reasoning cannot resolve missing authority or missing facts. Stop without
escalation for:

- A missing product or human decision.
- Conflicting approved human decisions.
- An architecture decision requiring human acceptance.
- Authorization failure.
- An unavailable dependency.
- Exhausted usage budget.

## Usage accounting

Record for every action:

- Role and action.
- Selected profile, model and reasoning effort.
- Routing inputs and reason.
- Input, output and total tokens when available.
- Start time, completion time and elapsed time.
- Retry and escalation history.
- Outcome and handoff.

Failed, malformed and retried calls count toward totals. Subscription-authenticated
Codex usage must not be converted into a claimed monetary API cost.

The issue activity comment contains proposal and planning usage. The pull-request
activity comment contains implementation, QA, review and repair usage. Both are
updated idempotently by the orchestrator.
