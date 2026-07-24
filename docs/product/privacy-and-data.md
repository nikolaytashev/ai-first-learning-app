# Privacy and Data Boundaries

The initial privacy model is not approved. This document defines constraints and
the decisions required before personal-data persistence or telemetry is built.

## Data-minimization constraints

- Collect only data needed for an approved product behaviour or operational
  obligation.
- Do not use advertising identifiers in the initial release.
- Do not send lesson or user data to a generative-AI service at runtime.
- Do not place personal data or credentials in agent prompts, GitHub issues,
  logs or test fixtures.
- Prefer aggregated or local-only measurement when it can answer the approved
  product question.

## Candidate data inventory

| Category | Example | Approval state |
| --- | --- | --- |
| Identity | Account ID, email or anonymous installation ID | Decision required |
| Learning progress | Lesson position, quiz attempts and completion | Scope approved; storage rules required |
| Preferences | Reminder schedule and time zone | Scope approved; retention rules required |
| Device data | App version, platform and crash context | Decision required |
| Product telemetry | Session and learning events | Decision required |
| Support data | User-provided report and diagnostic context | Decision required |

## Decisions required

- Identity and lawful-basis model.
- Data controller details and processors.
- Data location and third-party services.
- Consent and preference-management behaviour.
- Retention periods for every persisted category.
- Export, correction and account-deletion behaviour.
- Backup deletion and operational-log redaction.
- Age restrictions.
- Security incident and breach-response process.
- Analytics and crash-reporting providers, if any.

Architecture and implementation work involving these categories must wait for
the relevant human decision and legal review appropriate to the launch market.
