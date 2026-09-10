from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"missing lint-fix anchor in {path}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "scripts/orchestrator/application_state.py",
    "Only remote refs are fetched and a detached worktree is maintained under the runtime state directory.\n",
    "Only remote refs are fetched. A detached worktree is maintained under the runtime state\ndirectory.\n",
)
replace(
    "scripts/orchestrator/autonomous_implementation.py",
    '                "Recovered interrupted workflow; no open owned PR was found, so the durable agent branch will be resumed as rework.",\n',
    '                "Recovered interrupted workflow; no open owned PR was found, so the durable "\n                "agent branch will be resumed as rework.",\n',
)
replace(
    "scripts/orchestrator/autonomous_implementation.py",
    '                "Identify binding technical boundaries and flag only decisions that require human architecture authority."\n',
    '                "Identify binding technical boundaries and flag only decisions that require "\n                "human architecture authority."\n',
)
replace(
    "scripts/orchestrator/autonomous_implementation.py",
    '                else "Identify binding learning-design constraints and flag only unresolved product/content decisions that require human authority."\n',
    '                else "Identify binding learning-design constraints and flag only unresolved "\n                "product/content decisions that require human authority."\n',
)
replace(
    "scripts/orchestrator/autonomous_implementation.py",
    '            "Independently verify every acceptance criterion, specialist constraint and regression risk."\n',
    '            "Independently verify every acceptance criterion, specialist constraint and "\n            "regression risk."\n',
)
replace(
    "scripts/orchestrator/autonomous_implementation.py",
    '            else "Independently review correctness, maintainability, security, architecture and specialist constraints."\n',
    '            else "Independently review correctness, maintainability, security, architecture "\n            "and specialist constraints."\n',
)
replace(
    "scripts/orchestrator/autonomous_implementation.py",
    '                    f"Feature-level QA passed against merged application commit {snapshot.commit_sha}.",\n',
    '                    f"Feature-level QA passed against merged application "\n                    f"commit {snapshot.commit_sha}.",\n',
)
replace(
    "scripts/orchestrator/control_plane.py",
    "object required by the schema and a specialists list. Mark learning_content true for learning-content\nauthoring/design. Request software_architect for architecture/security/data/concurrency-sensitive work\n",
    "object required by the schema and a specialists list. Mark learning_content true for\nlearning-content authoring/design. Request software_architect for architecture/security/data/\nconcurrency-sensitive work\n",
)
