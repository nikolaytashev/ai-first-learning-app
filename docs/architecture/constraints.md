# Architecture Constraints

## Approved direction

- The primary client is a Flutter mobile application.
- The mobile experience is offline-first for approved learning flows; initial
  content caching remains limited to previously opened lessons.
- The backend is built with .NET and PostgreSQL.
- The first release uses simple architecture; microservices are an explicit
  non-goal.
- The public website is presentational and is not a full web equivalent of the
  mobile application.
- The initial product has no runtime generative-AI dependency.
- Previously opened lessons require limited offline access.
- GitHub Issues and Projects form the autonomous-development control plane.
- The autonomous orchestrator runs locally and initially uses Codex CLI.
- Git-backed Obsidian content is an editing view; committed Git content remains
  the source of truth.
- Graph-derived context may be a generated retrieval index, but it may not
  replace source documents, Git history or architecture decisions.

## Engineering implications

- Prefer a modular monolith until measured scaling or ownership needs justify a
  split.
- Keep mobile persistence and synchronization behind explicit interfaces
  because identity and conflict rules are unresolved.
- Version learning content and its local representation.
- Keep notification scheduling isolated from learning-domain logic.
- Treat accessibility, localization, observability, security and data deletion
  as cross-cutting requirements in feature acceptance criteria.
- Do not select a third-party analytics, notification, identity or content
  service without an architecture decision and privacy review.

## Decisions required before product implementation

- Identity and authorization design.
- Offline storage and synchronization model.
- API style and versioning policy.
- Content authoring and delivery pipeline.
- Hosting regions and deployment topology.
- Notification provider and server-versus-device scheduling.
- Observability and telemetry providers.
- Recovery objectives, service-level targets and capacity assumptions.
