from pathlib import Path

ROOT = Path('.')

def replace(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'anchor missing in {path}: {old[:100]!r}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')

# Reconciliation schema: persist the classification dimensions already required by model policy.
path = ROOT / 'schemas/reconciliation-plan.schema.json'
text = path.read_text(encoding='utf-8')
old = '"required": ["key", "type", "existing_issue_number", "title", "description", "acceptance_criteria", "priority", "size", "risk", "specialist_roles", "dependencies"]'
new = '"required": ["key", "type", "existing_issue_number", "title", "description", "acceptance_criteria", "priority", "size", "risk", "ambiguity", "affected_areas", "security_sensitive", "persistent_data_change", "destructive_migration", "architecture_change", "user_visible_change", "concurrency_sensitive", "data_loss_risk", "previous_failures", "specialist_roles", "dependencies"]'
if old not in text:
    raise SystemExit('reconciliation required anchor missing')
text = text.replace(old, new, 1)
old = '''          "risk": {"enum": ["low", "medium", "high", "critical"]},
          "specialist_roles": {'''
new = '''          "risk": {"enum": ["low", "medium", "high", "critical"]},
          "ambiguity": {"enum": ["low", "medium", "high"]},
          "affected_areas": {
            "type": "array",
            "uniqueItems": true,
            "items": {"type": "string", "minLength": 1}
          },
          "security_sensitive": {"type": "boolean"},
          "persistent_data_change": {"type": "boolean"},
          "destructive_migration": {"type": "boolean"},
          "architecture_change": {"type": "boolean"},
          "user_visible_change": {"type": "boolean"},
          "concurrency_sensitive": {"type": "boolean"},
          "data_loss_risk": {"type": "boolean"},
          "previous_failures": {"type": "integer", "minimum": 0},
          "specialist_roles": {'''
if old not in text:
    raise SystemExit('reconciliation risk anchor missing')
path.write_text(text.replace(old, new, 1), encoding='utf-8')

# BA prompt + metadata persistence.
replace(
    'scripts/orchestrator/control_plane.py',
    '''`specialist_roles`: include `software_architect` when architecture, security, privacy, persistence,
data integrity, destructive migration, concurrency, or significant cross-component boundaries need
independent technical design/review; include `instructional_designer` when the task creates or
materially changes learning objectives, lessons, exercises, assessments, pathways, or pedagogical
content. Use an empty list when no specialist is required.''',
    '''`specialist_roles`: include `software_architect` when architecture, security, privacy, persistence,
data integrity, destructive migration, concurrency, or significant cross-component boundaries need
independent technical design/review; include `instructional_designer` when the task creates or
materially changes learning objectives, lessons, exercises, assessments, pathways, or pedagogical
content. Use an empty list when no specialist is required. Also classify every child using the
approved model-routing dimensions: ambiguity, affected_areas, security_sensitive,
persistent_data_change, destructive_migration, architecture_change, user_visible_change,
concurrency_sensitive, and data_loss_risk. `previous_failures` is orchestrator-owned: preserve the
current value for reused Tasks and use 0 for new work.''',
)
replace(
    'scripts/orchestrator/control_plane.py',
    '''                child_meta["specialist_roles"] = item.get("specialist_roles", [])
                body = self._child_body(child.body, child_meta, item)''',
    '''                child_meta["specialist_roles"] = item.get("specialist_roles", [])
                for field in (
                    "ambiguity",
                    "affected_areas",
                    "security_sensitive",
                    "persistent_data_change",
                    "destructive_migration",
                    "architecture_change",
                    "user_visible_change",
                    "concurrency_sensitive",
                    "data_loss_risk",
                ):
                    child_meta[field] = item.get(field)
                child_meta["previous_failures"] = int(
                    child_meta.get("previous_failures", item.get("previous_failures", 0)) or 0
                )
                body = self._child_body(child.body, child_meta, item)''',
)
replace(
    'scripts/orchestrator/control_plane.py',
    '''                child_meta["specialist_roles"] = item.get("specialist_roles", [])
                marker = _metadata_marker(child_meta)''',
    '''                child_meta["specialist_roles"] = item.get("specialist_roles", [])
                for field in (
                    "ambiguity",
                    "affected_areas",
                    "security_sensitive",
                    "persistent_data_change",
                    "destructive_migration",
                    "architecture_change",
                    "user_visible_change",
                    "concurrency_sensitive",
                    "data_loss_risk",
                    "previous_failures",
                ):
                    child_meta[field] = item.get(field)
                marker = _metadata_marker(child_meta)''',
)
replace(
    'scripts/orchestrator/control_plane.py',
    '''            "specialist_roles": [],
        }''',
    '''            "specialist_roles": [],
            "ambiguity": "low",
            "affected_areas": [],
            "security_sensitive": False,
            "persistent_data_change": False,
            "destructive_migration": False,
            "architecture_change": False,
            "user_visible_change": False,
            "concurrency_sensitive": False,
            "data_loss_risk": False,
            "previous_failures": 0,
        }''',
)

# Select-model: execute the declared routing rules rather than only size/risk.
config = ROOT / 'scripts/orchestrator/config.py'
text = config.read_text(encoding='utf-8')
old = '''    *,
    size: str | None = None,
    risk: str | None = None,
) -> ModelSelection:'''
new = '''    *,
    size: str | None = None,
    risk: str | None = None,
    ambiguity: str | None = None,
    architecture_change: bool = False,
    security_sensitive: bool = False,
    destructive_migration: bool = False,
    data_loss_risk: bool = False,
    previous_failures: int = 0,
) -> ModelSelection:'''
if old not in text:
    raise SystemExit('select_model signature anchor missing')
text = text.replace(old, new, 1)
old = '''    if profile_name not in allowed:
        raise ValueError(f"profile {profile_name!r} is not allowed for role {role!r}")
    if attempt >= 3:
        current_index = allowed.index(profile_name)
        if current_index + 1 < len(allowed):
            profile_name = allowed[current_index + 1]

    profile = _mapping(profiles.get(profile_name), f"profiles.{profile_name}")'''
new = '''    if profile_name not in allowed:
        raise ValueError(f"profile {profile_name!r} is not allowed for role {role!r}")

    capability_order = ("text_light", "code_light", "balanced", "deep", "critical")

    def upgrade_one(current: str) -> str:
        index = allowed.index(current)
        return allowed[index + 1] if index + 1 < len(allowed) else current

    def minimum_profile(current: str, minimum: str) -> str:
        minimum_rank = capability_order.index(minimum)
        current_rank = capability_order.index(current)
        if current_rank >= minimum_rank:
            return current
        eligible = [
            candidate
            for candidate in allowed
            if capability_order.index(candidate) >= minimum_rank
        ]
        return eligible[0] if eligible else allowed[-1]

    if ambiguity == "high":
        profile_name = upgrade_one(profile_name)
    if architecture_change:
        profile_name = minimum_profile(profile_name, "balanced")
    if security_sensitive:
        profile_name = minimum_profile(profile_name, "deep")
    if destructive_migration or data_loss_risk:
        profile_name = minimum_profile(profile_name, "critical")
    if previous_failures >= 2:
        profile_name = upgrade_one(profile_name)
    if attempt >= 3:
        profile_name = upgrade_one(profile_name)

    profile = _mapping(profiles.get(profile_name), f"profiles.{profile_name}")'''
if old not in text:
    raise SystemExit('select_model routing anchor missing')
config.write_text(text.replace(old, new, 1), encoding='utf-8')

# Pass Task/Feature classification into every implementation-side role.
impl = ROOT / 'scripts/orchestrator/implementation.py'
text = impl.read_text(encoding='utf-8')
old = '''        size: str,
        risk: str,
    ) -> JsonObject:'''
new = '''        size: str,
        risk: str,
        classification: Mapping[str, Any] | None = None,
    ) -> JsonObject:'''
if old not in text:
    raise SystemExit('implementation _run_agent signature anchor missing')
text = text.replace(old, new, 1)
old = '''            model = select_model(
                self._config,
                role,
                action,
                attempt,
                size=size,
                risk=risk,
            )'''
new = '''            routing = classification or {}
            model = select_model(
                self._config,
                role,
                action,
                attempt,
                size=size,
                risk=risk,
                ambiguity=str(routing.get("ambiguity") or "low"),
                architecture_change=routing.get("architecture_change") is True,
                security_sensitive=routing.get("security_sensitive") is True,
                destructive_migration=routing.get("destructive_migration") is True,
                data_loss_risk=routing.get("data_loss_risk") is True,
                previous_failures=int(routing.get("previous_failures", 0) or 0),
            )'''
if old not in text:
    raise SystemExit('implementation select_model anchor missing')
text = text.replace(old, new, 1)
# Add classification=metadata to all role calls that have metadata in scope.
needle = '''            size=str(metadata.get("size") or "M"),
            risk=str(metadata.get("risk") or "medium"),
        )'''
replacement = '''            size=str(metadata.get("size") or "M"),
            risk=str(metadata.get("risk") or "medium"),
            classification=metadata,
        )'''
count = text.count(needle)
if count < 3:
    raise SystemExit(f'expected at least 3 metadata agent calls, found {count}')
text = text.replace(needle, replacement)
# Count closed-without-merge/corrective exhaustion as prior failures for future routing.
old = '''                metadata["execution_state"] = "rework"
                metadata["pr_number"] = None
                self._update_metadata(task.number, metadata)'''
new = '''                metadata["execution_state"] = "rework"
                metadata["pr_number"] = None
                metadata["previous_failures"] = int(metadata.get("previous_failures", 0) or 0) + 1
                self._update_metadata(task.number, metadata)'''
if old not in text:
    raise SystemExit('closed PR rework anchor missing')
text = text.replace(old, new, 1)
old = '''        metadata["execution_state"] = "blocked"
        self._update_metadata(task.number, metadata)
        self._set_project(task, "Blocked", "Approved", "Human", "Failed")'''
new = '''        metadata["execution_state"] = "blocked"
        metadata["previous_failures"] = int(metadata.get("previous_failures", 0) or 0) + 1
        self._update_metadata(task.number, metadata)
        self._set_project(task, "Blocked", "Approved", "Human", "Failed")'''
if old not in text:
    raise SystemExit('block-after-exhaustion anchor missing')
text = text.replace(old, new, 1)
# Fix now-inaccurate recovery audit wording.
text = text.replace(
    '"regenerated on the existing agent branch."',
    '"regenerated on a fresh workflow-scoped agent branch."',
    1,
)
impl.write_text(text, encoding='utf-8')

# Direct unit coverage for routing semantics.
(ROOT / 'tests/test_model_routing_execution.py').write_text('''from pathlib import Path\n\nfrom scripts.orchestrator.config import load_config, select_model\n\nROOT = Path(__file__).resolve().parents[1]\n\n\ndef selected(role: str = "implementer", **kwargs: object) -> str:\n    config = load_config(ROOT)\n    return select_model(config, role, "implementation" if role == "implementer" else "review", 1, **kwargs).profile\n\n\ndef test_high_ambiguity_escalates_one_allowed_profile() -> None:\n    assert selected(size="M", risk="medium", ambiguity="high") == "deep"\n\n\ndef test_architecture_change_sets_balanced_floor() -> None:\n    assert selected(size="S", risk="low", architecture_change=True) == "balanced"\n\n\ndef test_security_sensitive_sets_deep_floor() -> None:\n    assert selected(size="S", risk="low", security_sensitive=True) == "deep"\n\n\ndef test_data_loss_selects_critical_when_role_allows_it() -> None:\n    assert selected(size="S", risk="low", data_loss_risk=True) == "critical"\n\n\ndef test_data_loss_caps_at_role_maximum_when_critical_is_not_allowed() -> None:\n    assert selected(role="qa", size="S", risk="low", data_loss_risk=True) == "deep"\n\n\ndef test_repeated_previous_failures_escalate_one_profile() -> None:\n    assert selected(size="S", risk="low", previous_failures=2) == "balanced"\n''', encoding='utf-8')
