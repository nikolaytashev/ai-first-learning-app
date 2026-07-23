# Initial User Journeys

These journeys describe the approved initial scope at a behaviour-outline
level. Rules marked as unresolved in `business-rules.md` remain human decisions.

## Start learning

1. A new user opens the mobile app.
2. The app explains the first learning pathway and completes lightweight
   onboarding.
3. The user opens the first available lesson.
4. The app records progress only through an approved local or account model.

## Complete a lesson and quiz

1. A user reads a short lesson.
2. The user starts the lesson quiz.
3. Each submitted answer receives an explanation.
4. The app calculates the result using the approved scoring rule.
5. The app marks progress using the approved completion rule.
6. The next lesson is shown according to the approved sequencing rule.

## Resume learning

1. A returning user sees the last meaningful learning position.
2. The user resumes the relevant lesson or quiz.
3. Locally stored and server-stored progress are reconciled using an approved
   conflict rule.
4. The user is warned rather than silently losing confirmed progress.

## Learn with limited connectivity

1. A user opens a lesson while online.
2. The app makes the lesson available offline within the approved storage and
   content-version rules.
3. The user reads the lesson while offline.
4. Progress is synchronized after connectivity returns.
5. Conflicts use the approved reconciliation rule.

## Configure a reminder

1. A user chooses whether to enable reminders.
2. The app requests operating-system permission only in response to that choice.
3. The user selects an allowed schedule.
4. Scheduling respects the user's current time zone and the approved
   daylight-saving behaviour.
5. The user can pause or disable reminders.
