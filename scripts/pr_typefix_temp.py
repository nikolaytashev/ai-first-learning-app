"""Temporary PR-only typing fixer; removed after use."""

from __future__ import annotations

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected patch context not found in {path}: {old!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    replace(
        "scripts/run_orchestrator.py",
        "from scripts.orchestrator.implementation import ImplementationWorkflow\n",
        "from scripts.orchestrator.implementation import ImplementationWorkflow\n"
        "from scripts.orchestrator.model import OrchestratorConfig\n",
    )
    replace(
        "scripts/run_orchestrator.py",
        "def _trusted_github() -> tuple[object, RuntimePolicySettings, GitHubClient]:\n",
        "def _trusted_github() -> tuple[OrchestratorConfig, RuntimePolicySettings, GitHubClient]:\n",
    )
    replace(
        "scripts/orchestrator/control_plane.py",
        '        classification = analysis.get("change_classification")\n'
        '        impact = plan.get("approval_impact")\n'
        '        required = {\n'
        '            "initial": "invalidate",\n'
        '            "material": "invalidate",\n'
        '            "uncertain": "decision_required",\n'
        '            "cancelled": "cancel",\n'
        '        }.get(classification)\n',
        '        classification = analysis.get("change_classification")\n'
        '        impact = plan.get("approval_impact")\n'
        '        required_by_classification = {\n'
        '            "initial": "invalidate",\n'
        '            "material": "invalidate",\n'
        '            "uncertain": "decision_required",\n'
        '            "cancelled": "cancel",\n'
        '        }\n'
        '        required = (\n'
        '            required_by_classification.get(classification)\n'
        '            if isinstance(classification, str)\n'
        '            else None\n'
        '        )\n',
    )
    replace(
        "scripts/orchestrator/control_plane.py",
        '                resolved[cast(str, key)].id for key in cast(list[str], item["dependencies"])\n',
        '                resolved[key].id for key in cast(list[str], item["dependencies"])\n',
    )


if __name__ == "__main__":
    main()
