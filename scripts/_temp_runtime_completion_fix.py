from pathlib import Path

path = Path("scripts/orchestrator/implementation.py")
text = path.read_text(encoding="utf-8")

replacements = [
    (
        '''self._audit(feature.number, f"Feature integration validation failed on origin/main `{app_sha}`:\n{findings}")''',
        '''self._audit(
                    feature.number,
                    (
                        f"Feature integration validation failed on origin/main `{app_sha}`:\\n"
                        f"{findings}"
                    ),
                )''',
    ),
    (
        '''"Recovered interrupted workflow; unpublished work will be safely regenerated on the existing agent branch."''',
        '''(
                        "Recovered interrupted workflow; unpublished work will be safely "
                        "regenerated on the existing agent branch."
                    )''',
    ),
    (
        '''"Define implementation constraints and technical boundaries. Do not approve human-owned "
                    "architecture decisions; return decision_required when such a decision is missing."''',
        '''"Define implementation constraints and technical boundaries. "
                    "Do not approve human-owned architecture decisions; return decision_required "
                    "when such a decision is missing."''',
    ),
    (
        '''"Define learning-design requirements for objectives, sequencing, exercises and assessment. "
                    "Do not invent unresolved product or technical facts."''',
        '''"Define learning-design requirements for objectives, sequencing, exercises and "
                    "assessment. Do not invent unresolved product or technical facts."''',
    ),
    (
        '''f"Feature integration validation failed on origin/main `{app_sha}`:\\n{findings}",''',
        '''(
                        f"Feature integration validation failed on origin/main `{app_sha}`:\\n"
                        f"{findings}"
                    ),''',
    ),
    (
        '''    def _validate_current_application_state(self, feature_number: int) -> tuple[ValidationRun, str]:
        """Validate the latest remote application state without updating the orchestrator checkout."""''',
        '''    def _validate_current_application_state(
        self, feature_number: int
    ) -> tuple[ValidationRun, str]:
        """Validate latest remote app state without moving the orchestrator checkout."""''',
    ),
]

for old, new in replacements:
    if old in text:
        text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
