"""Autonomous control-plane extensions for task classification and specialist routing."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from scripts.orchestrator.control_plane import _replace_metadata, parse_metadata
from scripts.orchestrator.model import IssueSnapshot, JsonObject
from scripts.orchestrator.safety_control import HardenedControlPlaneWorkflow

_TECHNICAL_SPECIALIST_FLAGS = {
    "architecture_change",
    "security_sensitive",
    "persistent_data_change",
    "destructive_migration",
    "concurrency_sensitive",
    "data_loss_risk",
}


class AutonomousControlPlaneWorkflow(HardenedControlPlaneWorkflow):
    """Persist BA classifications and enforce specialist routing invariants."""

    def _apply_plan(
        self,
        parent: IssueSnapshot,
        metadata: JsonObject,
        analysis: Mapping[str, Any],
        plan: Mapping[str, Any],
        children: list[IssueSnapshot],
    ) -> None:
        super()._apply_plan(parent, metadata, analysis, plan, children)
        raw_desired = plan.get("desired_children")
        if not isinstance(raw_desired, list):
            return

        current_children = self._github.list_sub_issues(parent.number)
        by_key: dict[str, IssueSnapshot] = {}
        for child in current_children:
            child_meta = parse_metadata(child.body)
            key = child_meta.get("key") if child_meta is not None else None
            if isinstance(key, str):
                by_key[key] = child

        for raw_item in raw_desired:
            if not isinstance(raw_item, Mapping):
                continue
            key = raw_item.get("key")
            classification = raw_item.get("classification")
            raw_specialists = raw_item.get("specialists")
            if (
                not isinstance(key, str)
                or not isinstance(classification, Mapping)
                or not isinstance(raw_specialists, list)
            ):
                raise RuntimeError("BA desired child omitted classification or specialists")
            child = by_key.get(key)
            if child is None:
                raise RuntimeError(f"could not resolve reconciled child key {key!r}")
            specialists = {value for value in raw_specialists if isinstance(value, str)}
            if any(classification.get(flag) is True for flag in _TECHNICAL_SPECIALIST_FLAGS):
                specialists.add("software_architect")
            if classification.get("learning_content") is True:
                specialists.add("instructional_designer")
            unsupported = specialists - {"software_architect", "instructional_designer"}
            if unsupported:
                raise RuntimeError(f"unsupported specialists in BA plan: {sorted(unsupported)}")

            child_meta = parse_metadata(child.body)
            if child_meta is None:
                raise RuntimeError(f"reconciled child #{child.number} lost orchestration metadata")
            child_meta["classification"] = dict(classification)
            child_meta["specialists"] = sorted(specialists)
            self._github.update_issue(
                child.number,
                body=_replace_metadata(child.body, child_meta),
            )
            if specialists:
                names = ", ".join(sorted(specialists))
                self._audit(child.number, f"Task routing requires specialist review: {names}.")
