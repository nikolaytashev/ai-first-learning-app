from pathlib import Path

path = Path("scripts/_temp_model_routing_patch.py")
text = path.read_text(encoding="utf-8")
start_marker = 'def selected(role: str = "implementer", **kwargs: object) -> str:\\n'
end_marker = '\\n\\n\\ndef test_high_ambiguity_escalates_one_allowed_profile()'
start = text.find(start_marker)
end = text.find(end_marker, start)
if start < 0 or end < 0:
    raise SystemExit("model-routing test helper boundaries not found")
new = '''def selected(\\n    role: str = "implementer",\\n    *,\\n    size: str | None = None,\\n    risk: str | None = None,\\n    ambiguity: str | None = None,\\n    architecture_change: bool = False,\\n    security_sensitive: bool = False,\\n    destructive_migration: bool = False,\\n    data_loss_risk: bool = False,\\n    concurrency_sensitive: bool = False,\\n    previous_failures: int = 0,\\n) -> str:\\n    config = load_config(ROOT)\\n    return select_model(\\n        config,\\n        role,\\n        "implementation" if role == "implementer" else "review",\\n        1,\\n        size=size,\\n        risk=risk,\\n        ambiguity=ambiguity,\\n        architecture_change=architecture_change,\\n        security_sensitive=security_sensitive,\\n        destructive_migration=destructive_migration,\\n        data_loss_risk=data_loss_risk,\\n        concurrency_sensitive=concurrency_sensitive,\\n        previous_failures=previous_failures,\\n    ).profile\\n'''
path.write_text(text[:start] + new + text[end:], encoding="utf-8")
