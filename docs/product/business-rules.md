# Product Business Rules

## Confirmed boundaries

- The first pathway is AI Fundamentals for Software Engineers.
- Lessons are followed by quizzes with answer explanations.
- Progress tracking, resume learning, reminders and limited offline access are
  part of the first vertical slice.
- Runtime generative AI, payments, advertising, social features and complex
  gamification are outside the initial scope.
- Educational content requires human review before publication.
- Product-visible behaviour requires human approval.

## Decisions required before implementation

### Identity and synchronization

- Whether the first release supports anonymous-only, optional-account or
  required-account usage.
- What data is stored locally and what is synchronized.
- Whether an anonymous profile can later be linked to an account.
- How two devices resolve conflicting progress.

### Quiz and completion

- Whether questions allow one answer, multiple answers or both.
- Whether answers can be changed before submission.
- The scoring formula, pass threshold and retry policy.
- When a lesson and pathway count as complete.
- Whether lesson order is locked, recommended or freely selectable.

### Offline behaviour

- Which content and media are cached.
- Cache lifetime, version invalidation and device storage limits.
- Whether offline quiz attempts are allowed.
- Conflict handling when content changes before synchronization.

### Reminders

- Allowed schedules and quiet hours.
- Time-zone and daylight-saving transitions.
- Behaviour after notification permission is denied.
- Whether reminder interaction is measured.

Each unresolved group must become a Decision issue. Feature acceptance criteria
must reference the resulting decision rather than duplicating an assumption.
