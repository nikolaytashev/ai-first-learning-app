from pathlib import Path

path = Path("scripts/_temp_dependency_snapshot_patch.py")
text = path.read_text(encoding="utf-8")
replacements = {
    'f"Feature integration validation failed on origin/main `{app_sha}`:\\n"': 'f"Feature integration validation failed on origin/main `{app_sha}`:\\\\n"',
    'f"Feature-level QA requires replanning:\\n{findings}"': 'f"Feature-level QA requires replanning:\\\\n{findings}"',
}
for old, new in replacements.items():
    if old not in text:
        raise SystemExit(f"missing newline-escaping anchor: {old}")
    text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
