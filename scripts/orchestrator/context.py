"""Task-scoped canonical context loading for agent runs."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import yaml

from scripts.orchestrator.model import JsonObject


def _load_index(root: Path) -> Mapping[str, Any]:
    raw = yaml.safe_load(
        (root / "docs/project-context/context-index.yaml").read_text(encoding="utf-8")
    )
    if not isinstance(raw, Mapping):
        raise ValueError("context-index root must be a mapping")
    return cast(Mapping[str, Any], raw)


def _safe_content_path(root: Path, relative_path: str) -> Path:
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"context path leaves repository: {relative_path}") from exc
    return candidate


def select_context_documents(
    root: Path,
    role: str,
    task_types: Sequence[str],
    *,
    content_root: Path | None = None,
) -> list[JsonObject]:
    """Load indexed context using trusted selection metadata and optionally fresh app content."""
    index = _load_index(root)
    raw_documents = index.get("documents")
    if not isinstance(raw_documents, list):
        raise ValueError("context-index documents must be a list")

    requested_tasks = set(task_types)
    selected: list[JsonObject] = []
    resolved_content_root = root if content_root is None else content_root
    for raw_entry in raw_documents:
        if not isinstance(raw_entry, Mapping):
            continue
        entry = cast(Mapping[str, Any], raw_entry)
        raw_consumers = entry.get("consumers")
        raw_tasks = entry.get("task_types")
        if not isinstance(raw_consumers, list) or not isinstance(raw_tasks, list):
            continue
        consumers = {item for item in raw_consumers if isinstance(item, str)}
        tasks = {item for item in raw_tasks if isinstance(item, str)}
        if role not in consumers and "all_agents" not in consumers:
            continue
        if "all" not in tasks and not requested_tasks.intersection(tasks):
            continue

        path_value = entry.get("path")
        authority_value = entry.get("authority")
        if not isinstance(path_value, str) or not isinstance(authority_value, str):
            continue
        trusted_path = _safe_content_path(root, path_value)
        fresh_path = _safe_content_path(resolved_content_root, path_value)
        path = fresh_path if fresh_path.is_file() else trusted_path
        selected.append(
            {
                "path": path_value,
                "authority": authority_value,
                "content": path.read_text(encoding="utf-8"),
            }
        )
    return selected


def render_context(documents: Sequence[JsonObject]) -> str:
    """Serialize context as inert JSON data rather than executable instructions."""
    return json.dumps(list(documents), ensure_ascii=False, indent=2, sort_keys=True)
