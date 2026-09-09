"""Temporary PR-only semantic lint fixer; removed after use."""

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
        "scripts/orchestrator/control_plane.py",
        "                if isinstance(artifact_type, str) and isinstance(origin, str):\n"
        '                    if artifact_type in {"Epic", "Feature", "Task"}:\n'
        "                        result.append(ManagedIssue(issue, artifact_type, origin, metadata))\n",
        "                if (\n"
        "                    isinstance(artifact_type, str)\n"
        "                    and isinstance(origin, str)\n"
        '                    and artifact_type in {"Epic", "Feature", "Task"}\n'
        "                ):\n"
        "                    result.append(\n"
        "                        ManagedIssue(issue, artifact_type, origin, metadata)\n"
        "                    )\n",
    )
    replace(
        "scripts/orchestrator/implementation.py",
        "from __future__ import annotations\n\nimport json\n",
        "from __future__ import annotations\n\n"
        "from collections.abc import Mapping\n\n"
        "import json\n",
    )
    replace(
        "scripts/orchestrator/implementation.py",
        '        """Reflect merged/closed orchestrator PRs into Task issue state without rewriting history."""\n',
        '        """Reflect merged/closed orchestrator PRs into Task state while preserving history."""\n',
    )
    replace(
        "scripts/orchestrator/implementation.py",
        '            self._set_project(feature, "In Review", "Approved", "QA", "Running")\n'
        '            prompt = f"""\n',
        '            self._set_project(feature, "In Review", "Approved", "QA", "Running")\n'
        "            completed_tasks = [\n"
        '                {"number": c.number, "title": c.title, "body": c.body}\n'
        "                for c in tasks\n"
        "            ]\n"
        "            completed_tasks_json = json.dumps(completed_tasks, ensure_ascii=False)\n"
        '            prompt = f"""\n',
    )
    replace(
        "scripts/orchestrator/implementation.py",
        '{json.dumps([{"number": c.number, "title": c.title, "body": c.body} for c in tasks], ensure_ascii=False)}\n',
        "{completed_tasks_json}\n",
    )
    replace(
        "scripts/run_orchestrator.py",
        "from pathlib import Path\n",
        "from pathlib import Path\nfrom typing import cast\n",
    )
    replace(
        "scripts/run_orchestrator.py",
        "    state: RuntimeStateStore | None = None\n"
        "    notifier: Notifier | None = None\n"
        "    iteration_id: int | None = None\n",
        "    state: RuntimeStateStore | None = None\n    iteration_id: int | None = None\n",
    )
    replace(
        "scripts/run_orchestrator.py",
        "        state = runtime_state\n"
        "        notifier = Notifier(settings.notifications)\n"
        "        waiting = workflow_state.latest_waiting()\n",
        "        state = runtime_state\n        waiting = workflow_state.latest_waiting()\n",
    )


if __name__ == "__main__":
    main()
