"""Regression tests for proposal context cost and BA acceptance quality."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.orchestrator.backlog import _completed_feature_context
from scripts.orchestrator.context import render_context, select_context_documents
from scripts.orchestrator.proposal import (
    _INLINE_POLICY_PATHS,
    _REFERENCE_ONLY_AUTHORITIES,
    ProposalWorkflow,
    _without_gate_only_decisions,
)


def root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_proposal_context_keeps_repository_policy_reference_only() -> None:
    documents = select_context_documents(
        root(),
        "product_manager",
        ["proposal_generation", "discovery"],
    )
    rendered = render_context(
        documents,
        reference_only_authorities=_REFERENCE_ONLY_AUTHORITIES,
        inline_paths=_INLINE_POLICY_PATHS,
    )
    payload = json.loads(rendered)
    by_path = {entry["path"]: entry for entry in payload}

    assert by_path["AGENTS.md"]["reference_only"] is True
    assert "content" not in by_path["AGENTS.md"]
    assert "content" in by_path["docs/product/initial-scope.md"]
    assert "content" in by_path["docs/product/human-decisions.md"]

    full = render_context(documents)
    assert len(rendered) < len(full) * 0.75


def test_completed_feature_history_is_bounded_and_scope_focused() -> None:
    body = (
        "## Problem\n"
        + "x" * 1000
        + "\n## Desired outcome\n"
        + "y" * 1000
        + "\n## Scope in\n- one\n- two\n## Scope out\n- three\n"
    )
    summary = _completed_feature_context(12, "Delivered feature", body)

    assert summary["number"] == 12
    assert summary["title"] == "Delivered feature"
    assert len(str(summary["problem"])) <= 500
    assert len(str(summary["desired_outcome"])) <= 500
    assert "one" in str(summary["scope_in"])
    assert "Scope out" not in str(summary["scope_in"])


def _proposal(*, size: str = "S") -> dict[str, object]:
    return {
        "size": size,
        "decisions_required": ["Choose the onboarding persistence model."],
    }


def _accepted_review(
    *, suggested_size: str = "S", decisions: list[str] | None = None
) -> dict[str, object]:
    return {
        "verdict": "accepted",
        "size_assessment": {
            "status": "appropriate",
            "suggested_size": suggested_size,
            "reason": "One bounded outcome.",
        },
        "decisions_required": (
            ["Choose the onboarding persistence model."] if decisions is None else decisions
        ),
        "required_revisions": [],
    }


def test_accepted_ba_review_with_size_mismatch_becomes_revision_required() -> None:
    normalized = ProposalWorkflow._apply_ba_acceptance_policy(
        _proposal(size="S"),
        _accepted_review(suggested_size="M"),
    )
    assert normalized["verdict"] == "revision_required"
    assert normalized["required_revisions"]


def test_ba_review_cannot_drop_human_decisions() -> None:
    normalized = ProposalWorkflow._apply_ba_acceptance_policy(
        _proposal(),
        _accepted_review(decisions=[]),
    )
    assert normalized["decisions_required"] == ["Choose the onboarding persistence model."]


def test_matching_accepted_ba_review_stays_accepted() -> None:
    normalized = ProposalWorkflow._apply_ba_acceptance_policy(
        _proposal(),
        _accepted_review(),
    )
    assert normalized["verdict"] == "accepted"


def test_proposal_context_includes_flutter_platform_constraints_for_pm_and_ba() -> None:
    pm_documents = select_context_documents(
        root(), "product_manager", ["proposal_generation", "discovery"]
    )
    ba_documents = select_context_documents(
        root(),
        "business_analysis",
        ["proposal_generation", "acceptance_criteria", "requirements"],
    )

    for documents in (pm_documents, ba_documents):
        by_path = {document["path"]: document for document in documents}
        constraints = by_path["docs/architecture/constraints.md"]
        assert "Flutter mobile application" in str(constraints["content"])


def test_standard_product_approval_is_not_a_domain_decision() -> None:
    normalized = _without_gate_only_decisions(
        {
            "status": "needs_decision",
            "decisions_required": [
                "Human approval of product scope and priority for this proposal.",
                "Approve or override the proposed P1 priority before implementation.",
                "Choose the canonical lesson-content contract.",
            ],
        }
    )

    assert normalized["decisions_required"] == ["Choose the canonical lesson-content contract."]
    assert normalized["status"] == "needs_decision"


def test_gate_only_decisions_downgrade_needs_decision_to_proposed() -> None:
    normalized = _without_gate_only_decisions(
        {
            "status": "needs_decision",
            "decisions_required": [
                "Human approval of product scope and priority for this proposal."
            ],
        }
    )

    assert normalized["decisions_required"] == []
    assert normalized["status"] == "proposed"
