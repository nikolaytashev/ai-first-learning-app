"""Restricted GitHub control-plane adapter for the proposal workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from scripts.orchestrator.model import IssueRef, JsonObject, OrchestratorConfig

_API = "https://api.github.com"
_GRAPHQL = "https://api.github.com/graphql"


@dataclass(frozen=True)
class ProjectField:
    """Resolved GitHub Project V2 field and option identifiers."""

    field_id: str
    data_type: str
    options: dict[str, str]


@dataclass(frozen=True)
class ProjectSnapshot:
    """Resolved GitHub Project V2 identity and field metadata."""

    project_id: str
    url: str
    fields: dict[str, ProjectField]


class GitHubClient:
    """Minimal GitHub REST/GraphQL client constrained to approved side effects."""

    def __init__(self, config: OrchestratorConfig, token: str) -> None:
        if not token:
            raise ValueError("GITHUB_TOKEN is required")
        self._config = config
        self._token = token

    def _request(
        self,
        method: str,
        url: str,
        payload: JsonObject | None = None,
    ) -> Any:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            url,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "ai-first-learning-local-orchestrator",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[-1000:]
            raise RuntimeError(
                f"GitHub request failed: {method} {url} -> {exc.code}: {detail}"
            ) from exc
        if not body:
            return None
        return json.loads(body)

    def _rest(self, method: str, path: str, payload: JsonObject | None = None) -> Any:
        return self._request(method, f"{_API}{path}", payload)

    def _graphql(self, query: str, variables: JsonObject) -> JsonObject:
        raw = self._request("POST", _GRAPHQL, {"query": query, "variables": variables})
        if not isinstance(raw, dict):
            raise RuntimeError("GitHub GraphQL response must be an object")
        response = cast(JsonObject, raw)
        errors = response.get("errors")
        if errors:
            raise RuntimeError(f"GitHub GraphQL request failed: {errors}")
        data = response.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("GitHub GraphQL response omitted data")
        return cast(JsonObject, data)

    def verify_identity_and_scope(self) -> list[str]:
        """Verify the supplied token belongs to the configured restricted identity."""
        errors: list[str] = []
        repo = self._config.repository.full_name
        raw_repo = self._rest("GET", f"/repos/{repo}")
        if not isinstance(raw_repo, dict) or raw_repo.get("full_name") != repo:
            errors.append(f"automation credential cannot read configured repository {repo}")
            return errors

        identity_type = self._config.authorization.automation_identity_type
        expected_login = self._config.authorization.automation_login
        if identity_type == "restricted_bot":
            raw_user = self._rest("GET", "/user")
            login = raw_user.get("login") if isinstance(raw_user, dict) else None
            if not expected_login:
                errors.append("GITHUB_AUTOMATION_LOGIN is required for restricted_bot")
            elif login != expected_login:
                errors.append(
                    f"authenticated GitHub login {login!r} does not match {expected_login!r}"
                )
        elif identity_type == "github_app":
            raw_installation = self._rest("GET", "/installation/repositories?per_page=100")
            repositories = (
                raw_installation.get("repositories") if isinstance(raw_installation, dict) else None
            )
            if not isinstance(repositories, list):
                errors.append("GITHUB_TOKEN is not a GitHub App installation access token")
            else:
                names = {
                    item.get("full_name")
                    for item in repositories
                    if isinstance(item, dict) and isinstance(item.get("full_name"), str)
                }
                if names != {repo}:
                    errors.append(
                        "GitHub App installation must expose exactly the configured repository"
                    )
        else:
            errors.append("GITHUB_AUTOMATION_IDENTITY_TYPE is not configured")
        return errors

    def project_snapshot(self) -> ProjectSnapshot:
        """Resolve the configured user/org Project V2 and all required fields."""
        number = self._config.project.number
        if number is None:
            raise RuntimeError("GitHub Project number is not configured")
        query = """
        query($login: String!, $number: Int!) {
          user(login: $login) {
            projectV2(number: $number) {
              id url fields(first: 100) {
                nodes {
                  ... on ProjectV2Field { id name dataType }
                  ... on ProjectV2IterationField { id name dataType }
                  ... on ProjectV2SingleSelectField { id name dataType options { id name } }
                }
              }
            }
          }
          organization(login: $login) {
            projectV2(number: $number) {
              id url fields(first: 100) {
                nodes {
                  ... on ProjectV2Field { id name dataType }
                  ... on ProjectV2IterationField { id name dataType }
                  ... on ProjectV2SingleSelectField { id name dataType options { id name } }
                }
              }
            }
          }
        }
        """
        data = self._graphql(
            query,
            {"login": self._config.project.owner, "number": number},
        )
        owner = data.get("user") or data.get("organization")
        project = owner.get("projectV2") if isinstance(owner, dict) else None
        if not isinstance(project, dict):
            raise RuntimeError("configured GitHub Project was not found")
        project_id = project.get("id")
        project_url = project.get("url")
        fields_container = project.get("fields")
        nodes = fields_container.get("nodes") if isinstance(fields_container, dict) else None
        if not isinstance(project_id, str) or not isinstance(project_url, str):
            raise RuntimeError("GitHub Project response omitted id/url")
        if not isinstance(nodes, list):
            raise RuntimeError("GitHub Project response omitted fields")

        fields: dict[str, ProjectField] = {}
        for raw_field in nodes:
            if not isinstance(raw_field, dict):
                continue
            field_id = raw_field.get("id")
            name = raw_field.get("name")
            data_type = raw_field.get("dataType")
            if not all(isinstance(value, str) for value in (field_id, name, data_type)):
                continue
            options_raw = raw_field.get("options")
            options: dict[str, str] = {}
            if isinstance(options_raw, list):
                for option in options_raw:
                    if not isinstance(option, dict):
                        continue
                    option_id = option.get("id")
                    option_name = option.get("name")
                    if isinstance(option_id, str) and isinstance(option_name, str):
                        options[option_name] = option_id
            fields[cast(str, name)] = ProjectField(
                field_id=cast(str, field_id),
                data_type=cast(str, data_type),
                options=options,
            )
        return ProjectSnapshot(project_id=project_id, url=project_url, fields=fields)

    def verify_project(self, project: ProjectSnapshot) -> list[str]:
        """Check Project V2 fields and options against config/github.yaml."""
        errors: list[str] = []
        configured_url = self._config.project.url
        if configured_url and project.url.rstrip("/") != configured_url.rstrip("/"):
            errors.append("configured GitHub Project URL does not match project number")
        for name, raw_contract in self._config.project.required_fields.items():
            field = project.fields.get(name)
            if field is None:
                errors.append(f"GitHub Project is missing required field {name!r}")
                continue
            if not isinstance(raw_contract, dict):
                errors.append(f"invalid field contract for {name!r}")
                continue
            expected_type = raw_contract.get("type")
            expected_github_type = {
                "single_select": "SINGLE_SELECT",
                "number": "NUMBER",
                "text": "TEXT",
            }.get(expected_type)
            if expected_github_type and field.data_type != expected_github_type:
                errors.append(
                    f"Project field {name!r} has type {field.data_type}, "
                    f"expected {expected_github_type}"
                )
            options = raw_contract.get("options")
            if isinstance(options, list):
                missing = [item for item in options if item not in field.options]
                if missing:
                    errors.append(f"Project field {name!r} is missing options: {missing}")
        return errors

    def verify_branch_rules(self) -> list[str]:
        """Verify active rules on main and reject any ruleset bypass actors."""
        errors: list[str] = []
        repo = self._config.repository.full_name
        branch = self._config.repository.default_branch
        rules_raw = self._rest("GET", f"/repos/{repo}/rules/branches/{branch}")
        if not isinstance(rules_raw, list):
            return ["unable to read active branch rules"]
        rules = [item for item in rules_raw if isinstance(item, dict)]
        rule_types = {item.get("type") for item in rules}
        for required in ("pull_request", "deletion", "non_fast_forward"):
            if required not in rule_types:
                errors.append(f"active {branch} rules are missing {required!r}")

        pull_rule = next((item for item in rules if item.get("type") == "pull_request"), None)
        if isinstance(pull_rule, dict):
            parameters = pull_rule.get("parameters")
            if not isinstance(parameters, dict) or not parameters.get(
                "required_review_thread_resolution"
            ):
                errors.append("main pull-request rule must require conversation resolution")

        check_rule = next(
            (item for item in rules if item.get("type") == "required_status_checks"),
            None,
        )
        contexts: set[str] = set()
        if isinstance(check_rule, dict):
            parameters = check_rule.get("parameters")
            raw_checks = (
                parameters.get("required_status_checks") if isinstance(parameters, dict) else None
            )
            if isinstance(raw_checks, list):
                contexts = {
                    check.get("context")
                    for check in raw_checks
                    if isinstance(check, dict) and isinstance(check.get("context"), str)
                }
        missing_checks = set(self._config.branch_policy.required_status_checks) - contexts
        if missing_checks:
            message = f"main rules are missing required status checks: {sorted(missing_checks)}"
            errors.append(message)

        rulesets_raw = self._rest("GET", f"/repos/{repo}/rulesets?includes_parents=false")
        if not isinstance(rulesets_raw, list) or not rulesets_raw:
            errors.append("repository has no active ruleset to protect main")
            return errors
        for summary in rulesets_raw:
            if not isinstance(summary, dict) or summary.get("enforcement") != "active":
                continue
            ruleset_id = summary.get("id")
            if not isinstance(ruleset_id, int):
                continue
            detail = self._rest("GET", f"/repos/{repo}/rulesets/{ruleset_id}")
            bypass = detail.get("bypass_actors") if isinstance(detail, dict) else None
            if isinstance(bypass, list) and bypass:
                errors.append(f"active ruleset {ruleset_id} contains bypass actors")
        return errors

    def find_issue_by_marker(self, marker: str) -> IssueRef | None:
        """Reconcile an issue by a stable hidden marker before creating a duplicate."""
        repo = self._config.repository.full_name
        for page in range(1, 6):
            query = urlencode({"state": "all", "per_page": 100, "page": page})
            raw = self._rest("GET", f"/repos/{repo}/issues?{query}")
            if not isinstance(raw, list):
                break
            for issue in raw:
                if not isinstance(issue, dict) or "pull_request" in issue:
                    continue
                if marker not in str(issue.get("body") or ""):
                    continue
                number = issue.get("number")
                node_id = issue.get("node_id")
                url = issue.get("html_url")
                if isinstance(number, int) and isinstance(node_id, str) and isinstance(url, str):
                    return IssueRef(number=number, node_id=node_id, url=url)
            if len(raw) < 100:
                break
        return None

    def create_issue(self, title: str, body: str) -> IssueRef:
        """Create one proposal issue in the configured repository."""
        repo = self._config.repository.full_name
        raw = self._rest("POST", f"/repos/{repo}/issues", {"title": title, "body": body})
        if not isinstance(raw, dict):
            raise RuntimeError("GitHub issue creation returned an invalid response")
        number = raw.get("number")
        node_id = raw.get("node_id")
        url = raw.get("html_url")
        if not isinstance(number, int) or not isinstance(node_id, str) or not isinstance(url, str):
            raise RuntimeError("GitHub issue creation omitted issue identity")
        return IssueRef(number=number, node_id=node_id, url=url)

    def add_to_project(self, project_id: str, issue_node_id: str) -> str:
        """Add an issue to Project V2 and return the item node ID."""
        query = """
        mutation($project: ID!, $content: ID!) {
          addProjectV2ItemById(input: {projectId: $project, contentId: $content}) {
            item { id }
          }
        }
        """
        data = self._graphql(query, {"project": project_id, "content": issue_node_id})
        payload = data.get("addProjectV2ItemById")
        item = payload.get("item") if isinstance(payload, dict) else None
        item_id = item.get("id") if isinstance(item, dict) else None
        if not isinstance(item_id, str):
            raise RuntimeError("GitHub Project item creation omitted item id")
        return item_id

    def update_project_fields(
        self,
        project: ProjectSnapshot,
        item_id: str,
        values: dict[str, str | int],
    ) -> None:
        """Set approved Project V2 fields on the proposal item."""
        mutation = """
        mutation($input: UpdateProjectV2ItemFieldValueInput!) {
          updateProjectV2ItemFieldValue(input: $input) { projectV2Item { id } }
        }
        """
        for name, value in values.items():
            field = project.fields.get(name)
            if field is None:
                raise RuntimeError(f"required Project field {name!r} was not resolved")
            field_value: JsonObject
            if field.data_type == "SINGLE_SELECT":
                option_id = field.options.get(str(value))
                if option_id is None:
                    raise RuntimeError(f"Project field {name!r} has no option {value!r}")
                field_value = {"singleSelectOptionId": option_id}
            elif field.data_type == "NUMBER":
                if not isinstance(value, int):
                    raise RuntimeError(f"Project field {name!r} requires an integer")
                field_value = {"number": value}
            elif field.data_type == "TEXT":
                field_value = {"text": str(value)}
            else:
                raise RuntimeError(f"unsupported Project field type {field.data_type}")
            self._graphql(
                mutation,
                {
                    "input": {
                        "projectId": project.project_id,
                        "itemId": item_id,
                        "fieldId": field.field_id,
                        "value": field_value,
                    }
                },
            )

    def find_comment_by_marker(self, issue_number: int, marker: str) -> str | None:
        """Reconcile an audit comment by hidden idempotency marker."""
        repo = self._config.repository.full_name
        for page in range(1, 6):
            query = urlencode({"per_page": 100, "page": page})
            raw = self._rest("GET", f"/repos/{repo}/issues/{issue_number}/comments?{query}")
            if not isinstance(raw, list):
                break
            for comment in raw:
                if not isinstance(comment, dict) or marker not in str(comment.get("body") or ""):
                    continue
                url = comment.get("url")
                if isinstance(url, str):
                    return url
            if len(raw) < 100:
                break
        return None

    def add_comment(self, issue_number: int, body: str) -> str:
        """Publish an audit comment and return its stable API URL."""
        repo = self._config.repository.full_name
        raw = self._rest(
            "POST",
            f"/repos/{repo}/issues/{issue_number}/comments",
            {"body": body},
        )
        url = raw.get("url") if isinstance(raw, dict) else None
        if not isinstance(url, str):
            raise RuntimeError("GitHub comment creation omitted URL")
        return url
