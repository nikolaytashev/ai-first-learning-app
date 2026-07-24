# Security Policy

## Supported versions

The project is in bootstrap development and has no supported production
release. Security fixes apply to the current `main` branch.

## Reporting a vulnerability

Do not create a public issue containing vulnerability details, credentials,
personal data or exploit instructions. Use GitHub's private vulnerability
reporting for this repository when available. If it is unavailable, contact the
repository owner privately through the contact method on the owner's GitHub
profile.

Include the affected component, impact, reproduction conditions and a safe
proof of concept. Do not access data that is not yours or disrupt a running
service.

## Secret handling

- Secrets are supplied to the trusted local orchestrator by an external secret
  provider.
- Secret values must not enter prompts, issue text, logs, source files,
  artifacts or agent-visible environment variables.
- Suspected exposure requires credential revocation and rotation before normal
  automation resumes.
- Autonomous agents may report that a credential is unavailable, but may not
  retrieve or inspect its value.
