from pathlib import Path

path = Path("scripts/_temp_model_routing_patch.py")
text = path.read_text(encoding="utf-8")

text = text.replace(
    '''    data_loss_risk: bool = False,
    previous_failures: int = 0,''',
    '''    data_loss_risk: bool = False,
    concurrency_sensitive: bool = False,
    previous_failures: int = 0,''',
    1,
)
text = text.replace(
    '''    if destructive_migration or data_loss_risk:
        profile_name = minimum_profile(profile_name, "critical")''',
    '''    if destructive_migration or data_loss_risk or concurrency_sensitive:
        profile_name = minimum_profile(profile_name, "critical")''',
    1,
)
text = text.replace(
    '''                data_loss_risk=routing.get("data_loss_risk") is True,
                previous_failures=int(routing.get("previous_failures", 0) or 0),''',
    '''                data_loss_risk=routing.get("data_loss_risk") is True,
                concurrency_sensitive=routing.get("concurrency_sensitive") is True,
                previous_failures=int(routing.get("previous_failures", 0) or 0),''',
    1,
)
text = text.replace(
    '''count = text.count(needle)
if count < 3:
    raise SystemExit(f'expected at least 3 metadata agent calls, found {count}')
text = text.replace(needle, replacement)''',
    '''count = text.count(needle)
if count < 2:
    raise SystemExit(f'expected at least 2 metadata agent calls, found {count}')
text = text.replace(needle, replacement)
feature_needle = ''' + "'''" + '''                size=str(metadata.get("size") or "M"),
                risk="medium",
            )''' + "'''" + '''
feature_replacement = ''' + "'''" + '''                size=str(metadata.get("size") or "M"),
                risk="medium",
                classification=metadata,
            )''' + "'''" + '''
if feature_needle not in text:
    raise SystemExit('Feature QA agent call classification anchor not found')
text = text.replace(feature_needle, feature_replacement, 1)''',
    1,
)
text = text.replace(
    '''def test_repeated_previous_failures_escalate_one_profile() -> None:\n    assert selected(size="S", risk="low", previous_failures=2) == "balanced"\n''',
    '''def test_concurrency_sensitive_selects_critical_when_role_allows_it() -> None:\n    assert selected(size="S", risk="low", concurrency_sensitive=True) == "critical"\n\n\ndef test_repeated_previous_failures_escalate_one_profile() -> None:\n    assert selected(size="S", risk="low", previous_failures=2) == "balanced"\n''',
    1,
)

path.write_text(text, encoding="utf-8")
