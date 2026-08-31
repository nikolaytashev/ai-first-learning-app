# Execution Budgets

Model routing is approved in `config/model-profiles.yaml`. The orchestrator must
enforce bounded concurrency, retries, elapsed time and usage warnings before
autonomous execution.

Codex is authenticated through a ChatGPT Plus subscription. Token measurements
are operational telemetry, not a precise monetary cost or a guaranteed provider
quota.

## Initial approved controls

| Control | Initial value |
| --- | ---: |
| Concurrent workflows | 1 |
| Concurrent role runs per workflow | 1 |
| Proposal workflow elapsed-time limit | 30 minutes |
| Implementation workflow elapsed-time limit | 120 minutes |
| Proposal workflow role runs | Product Manager and Business Analyst |
| Malformed-output correction | 1 per role action |
| Agent attempts per action | 3 |
| Implementer corrective cycles | 3 |
| Reviewer corrective cycles | 2 |
| Automatic model escalations per action | 2 |
| Action token warning | 120,000 measured tokens |
| Workflow token warning | 500,000 measured tokens |
| Daily hard token limit | Not set until subscription telemetry proves reliable |

The token thresholds are warnings. An absent or partial usage event must be
recorded as unavailable or partial, never as zero.

## Subscription reserve guard

The checked-in defaults in `config/orchestrator.yaml` preserve capacity for
interactive work on the same ChatGPT account:

| Reserve | Default |
| --- | ---: |
| 5-hour minimum remaining | 60% |
| Long-term minimum remaining | 40% |

The 5-hour and long-term checks have independent `enabled` switches. The 5-hour
window is optional by default because OpenAI may temporarily stop returning it.
The long-term guard identifies windows by duration, so a weekly window can be
replaced by a monthly window without changing the policy. Exactly 60%/40% is
allowed; work is skipped only below the configured reserve.

## Per-iteration hard budget

Every real iteration uses hard counters before side effects are started:

| Control | Default |
| --- | ---: |
| AI requests | 12 |
| Tasks processed | 3 |
| Pull Requests created | 1 |

Failed and retried AI requests count. The current proposal workflow consumes one
task and no Pull Request; the PR counter is already available for the future
implementation workflow.

## Execution gates

The proposal workflow may run when:

- The GitHub Project number and required fields are configured.
- The restricted automation identity is available.
- Repository validation passes.
- The Product Manager and Business Analyst output schemas are implemented.
- Usage and elapsed-time accounting are implemented.
- Runtime scheduling, repository-health and iteration-budget gates permit work.

The implementation workflow may run when:

- The proposal workflow has completed successfully.
- The issue has valid human approval.
- Worktree isolation, validation, QA, review and corrective routing exist.
- Draft pull-request creation and idempotent audit comments are implemented.
- The default branch remains protected.

## Enforcement rules

- Check remaining attempts, elapsed time and measured usage before every role
  run.
- Count failed, malformed and retried calls.
- Do not truncate an agent result and report success.
- Publish usage totals and elapsed time without prompts, secrets or raw private
  logs.
- Use deterministic Python validation instead of model-driven standard test
  execution.
- Stop with `BUDGET_EXHAUSTED` when a hard limit is reached.
- Exceeding a warning requires an audit event but does not silently cancel a
  completed atomic action.
- Budget changes require an allow-listed human and apply only to future runs
  unless `resume` explicitly reauthorizes a blocked failure streak.
- Critical profile selection requires an activation condition recorded in the
  action audit.
