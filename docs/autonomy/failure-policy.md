# Failure and Retry Policy

## Outcome classes

Every unsuccessful role run returns a schema-valid handoff with one of:

- `blocked`: progress requires a missing dependency or human decision.
- `failed`: execution or validation failed and may be retryable.
- `needs_input`: the responsible role must supply specific information.

Stable reason codes use uppercase snake case. Initial codes include
`PRODUCT_DECISION_REQUIRED`, `ARCHITECTURE_DECISION_REQUIRED`,
`INVALID_AGENT_OUTPUT`, `ACCEPTANCE_CRITERION_FAILED`, `VALIDATION_FAILED`,
`DEPENDENCY_UNAVAILABLE`, `AUTHORIZATION_DENIED`, `BUDGET_EXHAUSTED`,
`RETRY_EXHAUSTED`, `UNTRUSTED_COMMAND` and `STATE_CONFLICT`.

## Initial retry limits

| Route | Maximum corrective attempts |
| --- | ---: |
| Implementer correction after implementation or build failure | 3 |
| QA rerun after a claimed correction | 2 |
| Reviewer correction cycle | 2 |
| Invalid structured output from the same role | 1 |
| Transient GitHub or network operation | 5 with exponential backoff |

An attempt counts when a role starts, even if it returns malformed output.
Transient control-plane retries do not rerun an agent.

## Routing

- QA defect or review finding → Implementer.
- Missing or inconsistent acceptance criteria → Business Analyst.
- Missing architecture decision → Software Architect.
- Product, privacy or security ambiguity → Human Owner through Business
  Analysis.
- Infrastructure or authorization failure → Orchestrator operator.
- Exhausted attempts or budget → Human Owner with state `Blocked`.

## Terminal behaviour

When a limit is reached, the orchestrator must stop, release its lease, preserve
the worktree and evidence, set Automation State to `Failed`, set Project Status
to `Blocked` and publish one concise failure summary. It must not start a fresh
workflow to evade a limit.

Human `/resume` is valid only after the blocking cause or budget has changed.
Retries never relax acceptance criteria, tests, security controls or required
review.
