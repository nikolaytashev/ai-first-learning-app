# Autonomous Roles

Roles define authority and deliverables, not personalities. A role run receives
only the context required for its task and returns schema-valid output.

| Role | Purpose | May produce | Must not do |
| --- | --- | --- | --- |
| Human Owner | Own product, risk and release decisions | Approvals, priorities, merges, releases and policy changes | Delegate human-only authority implicitly |
| Orchestrator | Enforce the state machine and execute validated side effects | Locks, audit records, validated transitions, branches and draft PRs | Make product decisions or expose credentials |
| Product Manager | Select valuable outcomes and propose product work | Epics, feature proposals, priorities and success hypotheses | Approve its proposals or invent unresolved behaviour |
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
- Product ambiguity returns through the Business Analyst to the Human
  Owner.
- Architecture ambiguity returns to the Software Architect, then to the Human
  Owner when the decision is human-owned.

## Model-selection policy

Model profiles and role defaults are proposed in `config/model-profiles.yaml`
and require human approval before execution. Selection must use the lowest-cost
profile that meets the role's evidence and reasoning needs:

- Product Manager and Business Analysis: balanced reasoning with structured
  output.
- Architect and complex Implementer work: deep code and systems reasoning.
- Routine Implementer work: balanced coding model, escalating only after
  evidence of insufficiency.
- QA: balanced reasoning with strong tool use and reproducibility.
- Reviewer: deep reasoning for security, concurrency, data-loss or architecture
  risk; balanced reasoning for low-risk diffs.
- Instructional Designer: balanced reasoning, escalating for complex curriculum
  consistency or assessment design.

Fallback to a more expensive tier requires an audit reason code. Model changes
do not expand the role's authority.
