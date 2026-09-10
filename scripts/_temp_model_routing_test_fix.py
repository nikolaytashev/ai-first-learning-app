from pathlib import Path

path = Path("scripts/_temp_model_routing_patch.py")
text = path.read_text(encoding="utf-8")
old = '''ROOT = Path(__file__).resolve().parents[1]\\n\\n\\ndef selected(role: str = \\"implementer\\", **kwargs: object) -> str:\\n    config = load_config(ROOT)\\n    return select_model(config, role, \\"implementation\\" if role == \\"implementer\\" else \\"review\\", 1, **kwargs).profile\\n'''
new = '''ROOT = Path(__file__).resolve().parents[1]\\n\\n\\ndef selected(\\n    role: str = \\"implementer\\",\\n    *,\\n    size: str | None = None,\\n    risk: str | None = None,\\n    ambiguity: str | None = None,\\n    architecture_change: bool = False,\\n    security_sensitive: bool = False,\\n    destructive_migration: bool = False,\\n    data_loss_risk: bool = False,\\n    concurrency_sensitive: bool = False,\\n    previous_failures: int = 0,\\n) -> str:\\n    config = load_config(ROOT)\\n    return select_model(\\n        config,\\n        role,\\n        \\"implementation\\" if role == \\"implementer\\" else \\"review\\",\\n        1,\\n        size=size,\\n        risk=risk,\\n        ambiguity=ambiguity,\\n        architecture_change=architecture_change,\\n        security_sensitive=security_sensitive,\\n        destructive_migration=destructive_migration,\\n        data_loss_risk=data_loss_risk,\\n        concurrency_sensitive=concurrency_sensitive,\\n        previous_failures=previous_failures,\\n    ).profile\\n'''
if old not in text:
    raise SystemExit("typed model-routing test helper anchor not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
