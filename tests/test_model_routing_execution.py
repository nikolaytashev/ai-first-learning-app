from pathlib import Path

from scripts.orchestrator.config import load_config, select_model

ROOT = Path(__file__).resolve().parents[1]


def selected(
    role: str = "implementer",
    *,
    size: str | None = None,
    risk: str | None = None,
    ambiguity: str | None = None,
    architecture_change: bool = False,
    security_sensitive: bool = False,
    destructive_migration: bool = False,
    data_loss_risk: bool = False,
    concurrency_sensitive: bool = False,
    previous_failures: int = 0,
) -> str:
    config = load_config(ROOT)
    return select_model(
        config,
        role,
        "implementation" if role == "implementer" else "review",
        1,
        size=size,
        risk=risk,
        ambiguity=ambiguity,
        architecture_change=architecture_change,
        security_sensitive=security_sensitive,
        destructive_migration=destructive_migration,
        data_loss_risk=data_loss_risk,
        concurrency_sensitive=concurrency_sensitive,
        previous_failures=previous_failures,
    ).profile


def test_high_ambiguity_escalates_one_allowed_profile() -> None:
    assert selected(size="M", risk="medium", ambiguity="high") == "deep"


def test_architecture_change_sets_balanced_floor() -> None:
    assert selected(size="S", risk="low", architecture_change=True) == "balanced"


def test_security_sensitive_sets_deep_floor() -> None:
    assert selected(size="S", risk="low", security_sensitive=True) == "deep"


def test_data_loss_selects_critical_when_role_allows_it() -> None:
    assert selected(size="S", risk="low", data_loss_risk=True) == "critical"


def test_data_loss_caps_at_role_maximum_when_critical_is_not_allowed() -> None:
    assert selected(role="qa", size="S", risk="low", data_loss_risk=True) == "deep"


def test_repeated_previous_failures_escalate_one_profile() -> None:
    assert selected(size="S", risk="low", previous_failures=2) == "balanced"
