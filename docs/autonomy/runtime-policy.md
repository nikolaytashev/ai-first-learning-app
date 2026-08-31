# Autonomous Runtime Policy

`config/orchestrator.yaml` is the source of truth for repeated autonomous
execution. The policy is evaluated before a real iteration starts; skipped
checks do not consume the daily iteration count.

## Default schedule

- Minimum interval: 30 minutes.
- Working hours: 09:00-22:00 in `Europe/Sofia`.
- Maximum real iterations per local day: 8.

The worker does not need to cache a prior usage decision. Every permitted
iteration reads fresh Codex subscription usage before agent work starts.

## Priority policy

Future task-processing workflows must call the shared priority helper before
selecting work. The default order is `P0`, `P1`, `technical-debt`, then
`enhancement`. Items carrying `blocked`, `human-required` or `do-not-autonomy`
are excluded. Matching is case-insensitive.

The current proposal workflow generates one proposal rather than consuming an
issue backlog, so priority selection is intentionally dormant until the
implementation/task workflow exists.

## Stop policy

Autonomous work is stopped before agent execution when any configured hard gate
is active:

- Three consecutive failed real iterations.
- A required default-branch build check is missing, pending or unsuccessful.
- An open Pull Request has a merge conflict.
- An open Pull Request carries `blocked` or `autonomy-blocking`.

After fixing a consecutive-failure cause, run:

```bash
python scripts/run_orchestrator.py resume
```

Repository-health conditions are re-read on each later invocation and therefore
do not require a manual reset after the remote problem is fixed.

## Notifications

Notifications are enabled by default with `provider: auto`. If
`ORCHESTRATOR_NOTIFICATION_WEBHOOK_URL` exists, the worker POSTs a JSON event to
that endpoint. Otherwise the same structured event is written to stderr.

The worker emits:

- One daily report after 21:00 local time, deduplicated per calendar day.
- Immediate critical-error events, deduplicated for repeated identical preflight
  failures.
- A notification when usage reserve blocks autonomous work, deduplicated until
  the relevant usage reset changes.
- A notification when failure or repository-health policy stops autonomous work.

Use the inspection commands without starting agents:

```bash
python scripts/run_orchestrator.py usage
python scripts/run_orchestrator.py policy
```
