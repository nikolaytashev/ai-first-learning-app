"""Validate the repository's machine-readable P0 contracts."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, cast
from urllib.parse import unquote

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

ROOT = Path(__file__).resolve().parents[1]
IGNORED_PARTS = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv"}
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")
REQUIRED_FILES = {
    ".env.example",
    ".github/CODEOWNERS",
    ".github/ISSUE_TEMPLATE/bug.yml",
    ".github/ISSUE_TEMPLATE/decision-required.yml",
    ".github/ISSUE_TEMPLATE/feature-proposal.yml",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".secrets.baseline",
    "AGENTS.md",
    "config/github.yaml",
    "config/model-profiles.yaml",
    "config/validation.yaml",
    "docs/autonomy/approval-policy.md",
    "docs/autonomy/budgets.md",
    "docs/autonomy/failure-policy.md",
    "docs/autonomy/roles.md",
    "docs/autonomy/security-model.md",
    "docs/autonomy/workflow.md",
    "docs/product/business-rules.md",
    "docs/product/content-governance.md",
    "docs/product/privacy-and-data.md",
    "docs/product/problem-statement.md",
    "docs/product/success-metrics.md",
    "docs/product/user-journeys.md",
    "docs/project-context/context-index.yaml",
    "pyproject.toml",
    "requirements-dev.txt",
    "requirements-dev.lock",
    "schemas/agent-result.schema.json",
    "schemas/feature-proposal.schema.json",
    "schemas/handoff.schema.json",
    "schemas/validation-report.schema.json",
}


def repository_files(suffixes: Iterable[str]) -> list[Path]:
    """Return repository files with the requested suffixes."""
    requested = set(suffixes)
    return sorted(
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and path.suffix in requested
        and not any(part in IGNORED_PARTS for part in path.relative_to(ROOT).parts)
    )


def load_yaml(path: Path) -> Any:
    """Load one YAML document."""
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_json(path: Path) -> Any:
    """Load one JSON document."""
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_required_files() -> list[str]:
    """Verify that the P0 contract pack is complete."""
    return [
        f"Missing required file: {path}"
        for path in sorted(REQUIRED_FILES)
        if not (ROOT / path).is_file()
    ]


def validate_structured_syntax() -> list[str]:
    """Parse all YAML and JSON and validate every JSON Schema definition."""
    errors: list[str] = []

    for path in repository_files({".yaml", ".yml"}):
        try:
            load_yaml(path)
        except yaml.YAMLError as exc:
            errors.append(f"{path.relative_to(ROOT)}: invalid YAML: {exc}")

    for path in repository_files({".json"}):
        try:
            document = load_json(path)
        except json.JSONDecodeError as exc:
            errors.append(f"{path.relative_to(ROOT)}: invalid JSON: {exc}")
            continue

        if path.parent == ROOT / "schemas":
            try:
                Draft202012Validator.check_schema(document)
            except SchemaError as exc:
                errors.append(f"{path.relative_to(ROOT)}: invalid JSON Schema: {exc.message}")

    return errors


def validate_context_index() -> list[str]:
    """Validate context-index metadata and repository references."""
    path = ROOT / "docs/project-context/context-index.yaml"
    try:
        raw_index = load_yaml(path)
    except yaml.YAMLError:
        return []

    if not isinstance(raw_index, Mapping):
        return ["docs/project-context/context-index.yaml: root must be a mapping"]

    errors: list[str] = []
    raw_levels = raw_index.get("authority_levels")
    authority_levels = set(raw_levels) if isinstance(raw_levels, Mapping) else set()
    raw_documents = raw_index.get("documents")
    if not isinstance(raw_documents, list):
        return ["docs/project-context/context-index.yaml: documents must be a list"]

    seen_paths: set[str] = set()
    for position, raw_entry in enumerate(raw_documents, start=1):
        location = f"context-index document #{position}"
        if not isinstance(raw_entry, Mapping):
            errors.append(f"{location}: entry must be a mapping")
            continue

        required = {
            "path",
            "title",
            "authority",
            "version",
            "last_reviewed",
            "consumers",
            "task_types",
        }
        missing = required - set(raw_entry)
        if missing:
            errors.append(f"{location}: missing fields: {', '.join(sorted(missing))}")
            continue

        raw_reference = raw_entry["path"]
        if not isinstance(raw_reference, str):
            errors.append(f"{location}: path must be a string")
            continue

        reference = Path(raw_reference)
        if reference.is_absolute() or ".." in reference.parts:
            errors.append(f"{location}: path must stay within the repository: {raw_reference}")
        elif not (ROOT / reference).is_file():
            errors.append(f"{location}: referenced file does not exist: {raw_reference}")

        if raw_reference in seen_paths:
            errors.append(f"{location}: duplicate path: {raw_reference}")
        seen_paths.add(raw_reference)

        authority = raw_entry["authority"]
        if authority not in authority_levels:
            errors.append(f"{location}: unknown authority: {authority}")

        for list_field in ("consumers", "task_types"):
            value = raw_entry[list_field]
            if (
                not isinstance(value, list)
                or not value
                or not all(isinstance(item, str) for item in value)
            ):
                errors.append(f"{location}: {list_field} must be a non-empty string list")

        for string_field in ("title", "version", "last_reviewed"):
            if not isinstance(raw_entry[string_field], str) or not raw_entry[string_field]:
                errors.append(f"{location}: {string_field} must be a non-empty string")

    return errors


def markdown_target(source: Path, raw_target: str) -> Path | None:
    """Resolve a local Markdown link, or return None for non-local targets."""
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    target = target.split(maxsplit=1)[0]
    target = target.split("#", maxsplit=1)[0]
    if not target or target.startswith(("http://", "https://", "mailto:", "app://")):
        return None

    decoded = unquote(target)
    if decoded.startswith("/"):
        return ROOT / decoded.lstrip("/")
    return source.parent / decoded


def validate_markdown_links() -> list[str]:
    """Check that relative Markdown links resolve inside the repository."""
    errors: list[str] = []
    for source in repository_files({".md"}):
        text = source.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(text):
            resolved = markdown_target(source, raw_target)
            if resolved is None:
                continue
            try:
                resolved.resolve().relative_to(ROOT.resolve())
            except ValueError:
                errors.append(f"{source.relative_to(ROOT)}: link leaves repository: {raw_target}")
                continue
            if not resolved.exists():
                errors.append(f"{source.relative_to(ROOT)}: broken local link: {raw_target}")
    return errors


def validate_issue_forms() -> list[str]:
    """Check the minimum GitHub issue-form structure and unique field IDs."""
    errors: list[str] = []
    forms = sorted((ROOT / ".github/ISSUE_TEMPLATE").glob("*.yml"))
    for path in forms:
        if path.name == "config.yml":
            continue
        raw_form = load_yaml(path)
        if not isinstance(raw_form, Mapping):
            errors.append(f"{path.relative_to(ROOT)}: issue form must be a mapping")
            continue
        for key in ("name", "description", "body"):
            if key not in raw_form:
                errors.append(f"{path.relative_to(ROOT)}: missing issue-form key: {key}")
        body = raw_form.get("body")
        if not isinstance(body, list):
            continue
        ids: list[str] = []
        for item in body:
            if isinstance(item, Mapping) and isinstance(item.get("id"), str):
                ids.append(cast(str, item["id"]))
        if len(ids) != len(set(ids)):
            errors.append(f"{path.relative_to(ROOT)}: issue-form IDs must be unique")
    return errors


def validate_github_configuration() -> list[str]:
    """Check cross-file repository-control invariants."""
    errors: list[str] = []
    config = load_yaml(ROOT / "config/github.yaml")
    if not isinstance(config, Mapping):
        return ["config/github.yaml: root must be a mapping"]

    repository = config.get("repository")
    if not isinstance(repository, Mapping) or repository.get("default_branch") != "main":
        errors.append(
            "config/github.yaml: repository.default_branch must match GitHub default main"
        )

    authorization = config.get("authorization")
    approvers = authorization.get("human_approvers") if isinstance(authorization, Mapping) else None
    if not isinstance(approvers, list) or "nikolaytashev" not in approvers:
        errors.append("config/github.yaml: initial human approver must include nikolaytashev")

    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    mission = (ROOT / "mission.yaml").read_text(encoding="utf-8")
    if "Push directly to `main`" not in agents:
        errors.append("AGENTS.md: direct-push rule must name the actual default branch")
    if "Do not push directly to main" not in mission:
        errors.append("mission.yaml: direct-push constraint must name the actual default branch")
    return errors


def validate_model_profiles() -> list[str]:
    """Validate model-profile references and the pre-approval execution gate."""
    path = ROOT / "config/model-profiles.yaml"
    config = load_yaml(path)
    if not isinstance(config, Mapping):
        return ["config/model-profiles.yaml: root must be a mapping"]

    errors: list[str] = []
    if (
        config.get("configuration_status") != "approved"
        and config.get("execution_enabled") is not False
    ):
        errors.append(
            "config/model-profiles.yaml: execution must stay disabled until "
            "configuration is approved"
        )

    raw_profiles = config.get("profiles")
    raw_defaults = config.get("role_defaults")
    if not isinstance(raw_profiles, Mapping) or not raw_profiles:
        errors.append("config/model-profiles.yaml: profiles must be a non-empty mapping")
        return errors
    if not isinstance(raw_defaults, Mapping):
        errors.append("config/model-profiles.yaml: role_defaults must be a mapping")
        return errors

    expected_roles = {
        "product_manager",
        "business_analysis",
        "software_architect",
        "instructional_designer",
        "implementer",
        "qa",
        "reviewer",
    }
    missing_roles = expected_roles - set(raw_defaults)
    if missing_roles:
        errors.append(
            "config/model-profiles.yaml: missing role defaults: " + ", ".join(sorted(missing_roles))
        )

    known_profiles = set(raw_profiles)
    for role, raw_role_config in raw_defaults.items():
        if not isinstance(raw_role_config, Mapping):
            errors.append(f"config/model-profiles.yaml: {role} configuration must be a mapping")
            continue

        references: list[object] = []
        for key in ("default", "risk_escalation", "critical_escalation"):
            if key in raw_role_config:
                references.append(raw_role_config[key])
        escalations = raw_role_config.get("allowed_escalations")
        if isinstance(escalations, list):
            references.extend(escalations)
        size_defaults = raw_role_config.get("default_by_size")
        if isinstance(size_defaults, Mapping):
            references.extend(size_defaults.values())

        for reference in references:
            if reference == "forbidden_split_required":
                continue
            if reference not in known_profiles:
                errors.append(
                    f"config/model-profiles.yaml: {role} references unknown profile {reference}"
                )

    return errors


def collect_errors() -> list[str]:
    """Run all repository-level P0 validations."""
    validators = (
        validate_required_files,
        validate_structured_syntax,
        validate_context_index,
        validate_markdown_links,
        validate_issue_forms,
        validate_github_configuration,
        validate_model_profiles,
    )
    return [error for validator in validators for error in validator()]


def main() -> int:
    """CLI entry point."""
    errors = collect_errors()
    if errors:
        print("Repository validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Repository validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
