# Execution Budgets

The autonomous implementation loop must remain disabled until the human owner
approves concrete token or usage limits and the always-on execution host. Retry
limits are already defined in `failure-policy.md`.

## Safe bootstrap defaults

These controls apply before implementation is enabled:

| Control | Initial value |
| --- | ---: |
| Concurrent workflows | 1 |
| Concurrent role runs per workflow | 1 |
| Proposal workflow elapsed-time limit | 30 minutes |
| Proposal workflow role runs | 2: Product Manager and Business Analysis |
| Proposal workflow retries | 0, except one malformed-output correction |
| Implementation workflow | Disabled |
| Automatic model-tier escalation | Disabled |

## Decisions required

- Always-on execution host and operating-system identity.
- Per-role and per-workflow token or provider-usage limits.
- Maximum implementation elapsed time.
- Maximum daily and monthly provider usage.
- Approved model names, reasoning levels and fallback order.
- Whether unused budget carries between corrective attempts.
- Human override process and audit reason.

## Enforcement rules

- Check remaining budget before every role run.
- Count failed and malformed runs.
- Stop with `BUDGET_EXHAUSTED`; do not truncate a result and treat it as success.
- Budget changes require an allow-listed human and apply only to future runs
  unless `/resume` explicitly reauthorizes a blocked workflow.
- Publish usage totals and elapsed time without prompt contents or secrets.
