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
        """        worked = (
            control_result.reconciled > 0
            or control_result.commands > 0
            or implementation_result.get("status") not in {"idle", "skipped_schedule"}
            or int(implementation_result.get("pr_outcomes_reconciled", 0) or 0) > 0
            or int(implementation_result.get("feature_checks", 0) or 0) > 0
        )
""",
        """        pr_outcomes_reconciled = implementation_result.get("pr_outcomes_reconciled", 0)
        feature_checks = implementation_result.get("feature_checks", 0)
        worked = (
            control_result.reconciled > 0
            or control_result.commands > 0
            or implementation_result.get("status") not in {"idle", "skipped_schedule"}
            or (isinstance(pr_outcomes_reconciled, int) and pr_outcomes_reconciled > 0)
            or (isinstance(feature_checks, int) and feature_checks > 0)
        )
""",
    )


if __name__ == "__main__":
    main()
