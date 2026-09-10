from pathlib import Path

path = Path("scripts/_temp_dependency_snapshot_patch.py")
text = path.read_text(encoding="utf-8")
replacements = {
    'f"Feature integration validation failed on origin/main `{app_sha}`:\\n"': 'f"Feature integration validation failed on origin/main `{app_sha}`:\\\\n"',
    'f"Feature-level QA requires replanning:\\n{findings}"': 'f"Feature-level QA requires replanning:\\\\n{findings}"',
    (
        "from contextlib import contextmanager\n"
        "from dataclasses import dataclass\n"
        "from pathlib import Path\n"
        "from typing import Iterator"
    ): (
        "from collections.abc import Iterator\n"
        "from contextlib import contextmanager\n"
        "from dataclasses import dataclass\n"
        "from pathlib import Path"
    ),
    '            f"BA evaluated and reconciled {len(requests)} agent-requested graph/decomposition change(s).",\\n': (
        '            (\\n'
        '                f"BA evaluated and reconciled {len(requests)} "\\n'
        '                "agent-requested graph/decomposition change(s)."\\n'
        '            ),\\n'
    ),
}
for old, new in replacements.items():
    if old not in text:
        raise SystemExit(f"missing generated-code fix anchor: {old}")
    text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
