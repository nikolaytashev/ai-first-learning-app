from pathlib import Path

path = Path("scripts/orchestrator/implementation.py")
text = path.read_text(encoding="utf-8")
old = '''self._audit(feature.number, f"Feature integration validation failed on origin/main `{app_sha}`:
{findings}")'''
new = '''self._audit(
                    feature.number,
                    f"Feature integration validation failed on origin/main `{app_sha}`:\\n{findings}",
                )'''
if old not in text:
    raise SystemExit("expected generated Feature QA audit anchor not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
