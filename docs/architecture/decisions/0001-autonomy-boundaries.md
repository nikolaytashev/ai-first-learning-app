# ADR 0001: Autonomous-Development Authority Boundaries

- Status: Accepted
- Date: 2026-07-23
- Decision owner: Human owner

## Context

The project will use local AI agents to propose and implement work. GitHub is
the remote control plane, while product approval, merge and release authority
remain human responsibilities.

## Decision

- Autonomous execution runs on a trusted local host.
- GitHub issues and auditable owner commands control approved work.
- Agents work only on non-default branches and submit draft pull requests.
- Agents cannot approve their own product proposal, merge, release, deploy,
  modify repository controls or access secret values.
- The trusted orchestrator may use restricted credentials without exposing
  their values to agents.
- Product behaviour, privacy and security ambiguity returns to the human owner.
- Every run produces structured, schema-valid audit evidence.

## Consequences

The system prioritizes control and traceability over maximum autonomy. An
always-on worker, restricted GitHub identity, idempotent workflow state and
explicit human approvals are required before unattended implementation is
enabled.
