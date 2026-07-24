# Autonomous Roles

Roles define authority and deliverables, not personalities. A role run receives
only the context required for its task and returns schema-valid output.

| Role | Purpose | May produce | Must not do |
| --- | --- | --- | --- |
| Human Owner | Own product, risk and release decisions | Approvals, priorities, merges, releases and policy changes | Delegate human-only authority implicitly |
| Orchestrator | Enforce the state machine and execute validated side effects | Locks, audit records, validated transitions, branches and draft PRs | Make product decisions or expose credentials |
| Product Manager | Select valuable outcomes and propose product work | Epics, feature proposals, priority recommendations and success hypotheses | Approve its proposals or invent unresolved behaviour |
| Business Analyst | Combine requirements analysis, documentation stewardship and issue planning | Context updates, decision requests, decomposed issues, acceptance criteria and traceability | Change product scope or accept architecture decisions |
| Software Architect | Define boundaries and technical decisions for approved work | Proposed ADRs, architecture plans, non-functional requirements and risk analysis | Accept human-owned ADRs or implement unrelated scope |
| Instructional Designer | Design effective learning objectives, lesson structures, exercises and assessments | Content specifications, lesson drafts, quiz drafts and learning-quality review | Publish unreviewed content or invent technical facts |
| Implementer | Implement one approved, bounded issue | Code, tests, migrations and implementation notes | Change acceptance criteria or self-approve validation |
| QA Agent | Independently verify acceptance criteria and regressions | Validation report, reproducible defects and evidence | Modify implementation or waive failed criteria |
| Reviewer | Independently review correctness, maintainability, security and architecture | Review findings and approval recommendation | Merge, release or replace required QA |

## Separation of duties

- A single role run cannot both implement and independently approve the same
  change.
- QA and Reviewer receive the approved issue, final diff and validation evidence
  directly from the orchestrator, not only an Implementer summary.
- Corrective work returns to the Implementer; QA and Reviewer do not patch code.
- Product ambiguity returns through the Business Analyst to the Human Owner.
- Architecture ambiguity returns to the Software Architect, then to the Human
  Owner when the decision is human-owned.
- The orchestrator, not an agent, selects the model profile and executes
  privileged GitHub, Git and validation actions.

## Model-selection policy

The human-approved model configuration is
[`config/model-profiles.yaml`](../../config/model-profiles.yaml). Detailed
routing and escalation instructions are in
[`model-routing.md`](model-routing.md).

Selection uses the lowest sufficient profile:

- Product Manager and Business Analyst use balanced reasoning for substantive
  analysis and a light text profile for mechanical updates.
- Software Architect uses deep reasoning by default and critical reasoning only
  for explicitly high-risk work.
- Instructional Designer uses balanced reasoning, with light metadata work and
  deep pathway design as explicit overrides.
- Implementer selection is primarily size-based, then raised by risk.
- QA starts light for small deterministic cases and uses balanced or deep
  reasoning for complex behaviour.
- Reviewer uses balanced reasoning for small low-risk diffs and deep reasoning
  for normal code review.
- Critical reasoning is exceptional and requires an activation condition and
  an auditable reason.

A model change never expands the role's authority. Missing human decisions,
authorization failures and unavailable dependencies stop the workflow rather
than trigger a more expensive model.
