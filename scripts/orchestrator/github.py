"""Restricted GitHub control-plane adapter for autonomous planning and delivery."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from scripts.orchestrator.github_auth import (
    GitHubTokenProvider,
    StaticGitHubTokenProvider,
)
from scripts.orchestrator.model import (
    IssueComment,
    IssueRef,
    IssueSnapshot,
    JsonObject,
    OrchestratorConfig,
    PullRequestSnapshot,
)

_API = "https://api.github.com"
_GRAPHQL = "https://api.github.com/graphql"


def _project_owner_field(project_url: str | None) -> str:
    """Resolve the GraphQL owner field from the canonical Project URL."""
    if not project_url:
        raise RuntimeError("GitHub Project URL is not configured")
    if "/users/" in project_url:
        return "user"
    if "/orgs/" in project_url:
        return "organization"
    raise RuntimeError("GitHub Project URL must identify a user or organization Project")


def _same_instant(left: object, right: object) -> bool:
    """Compare GitHub ISO-8601 timestamps by instant rather than raw formatting."""
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    try:
        left_time = datetime.fromisoformat(left.replace("Z", "+00:00"))
        right_time = datetime.fromisoformat(right.replace("Z", "+00:00"))
    except ValueError:
        return False
    return left_time == right_time


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
    """GitHub REST/GraphQL adapter constrained to approved control-plane effects."""

    def __init__(
        self,
        config: OrchestratorConfig,
        token: str | GitHubTokenProvider,
    ) -> None:
        self._config = config
        self._token_provider = StaticGitHubTokenProvider(token) if isinstance(token, str) else token

    @property
    def token_provider(self) -> GitHubTokenProvider:
        """Return the trusted renewable credential provider used by this client."""
        return self._token_provider

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
                "Authorization": f"Bearer {self._token_provider.token()}",
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

    @staticmethod
    def _issue(raw: object) -> IssueSnapshot:
        if not isinstance(raw, dict):
            raise RuntimeError("GitHub issue response must be an object")
        database_id = raw.get("id")
        number = raw.get("number")
        node_id = raw.get("node_id")
        url = raw.get("html_url")
        title = raw.get("title")
        state = raw.get("state")
        user = raw.get("user")
        author = user.get("login") if isinstance(user, dict) else None
        if (
            not isinstance(database_id, int)
            or not isinstance(number, int)
            or not isinstance(node_id, str)
            or not isinstance(url, str)
            or not isinstance(title, str)
            or not isinstance(state, str)
            or not isinstance(author, str)
        ):
            raise RuntimeError("GitHub issue response omitted required identity fields")
        labels_raw = raw.get("labels")
        labels: list[str] = []
        if isinstance(labels_raw, list):
            for item in labels_raw:
                if isinstance(item, dict) and isinstance(item.get("name"), str):
                    labels.append(cast(str, item["name"]))
        state_reason = raw.get("state_reason")
        return IssueSnapshot(
            id=database_id,
            number=number,
            node_id=node_id,
            url=url,
            title=title,
            body=str(raw.get("body") or ""),
            state=state,
            state_reason=state_reason if isinstance(state_reason, str) else None,
            author=author,
            labels=tuple(labels),
        )

    @staticmethod
    def _pull_request(raw: object) -> PullRequestSnapshot:
        if not isinstance(raw, dict):
            raise RuntimeError("GitHub pull request response must be an object")
        number = raw.get("number")
        url = raw.get("html_url")
        state = raw.get("state")
        draft = raw.get("draft")
        head = raw.get("head")
        head_ref = head.get("ref") if isinstance(head, dict) else None
        if (
            not isinstance(number, int)
            or not isinstance(url, str)
            or not isinstance(state, str)
            or not isinstance(draft, bool)
            or not isinstance(head_ref, str)
        ):
            raise RuntimeError("GitHub pull request response omitted required fields")
        merged_at = raw.get("merged_at")
        return PullRequestSnapshot(
            number=number,
            url=url,
            state=state,
            draft=draft,
            merged_at=merged_at if isinstance(merged_at, str) else None,
            head_ref=head_ref,
            body=str(raw.get("body") or ""),
        )

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
        owner_field = _project_owner_field(self._config.project.url)
        query = f"""
        query($login: String!, $number: Int!) {{
          {owner_field}(login: $login) {{
            projectV2(number: $number) {{
              id url fields(first: 100) {{
                nodes {{
                  ... on ProjectV2Field {{ id name dataType }}
                  ... on ProjectV2IterationField {{ id name dataType }}
                  ... on ProjectV2SingleSelectField {{ id name dataType options {{ id name }} }}
                }}
              }}
            }}
          }}
        }}
        """
        data = self._graphql(
            query,
            {"login": self._config.project.owner, "number": number},
        )
        owner = data.get(owner_field)
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
            type_map = {
                "single_select": "SINGLE_SELECT",
                "number": "NUMBER",
                "text": "TEXT",
            }
            expected_github_type = (
                type_map.get(expected_type) if isinstance(expected_type, str) else None
            )
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

    def _single_select_option_inputs(self, field_id: str) -> list[JsonObject]:
        """Read option definitions so updates preserve existing option identities."""
        query = """
        query($id: ID!) {
          node(id: $id) {
            ... on ProjectV2SingleSelectField {
              options { id name color description }
            }
          }
        }
        """
        data = self._graphql(query, {"id": field_id})
        node = data.get("node")
        raw_options = node.get("options") if isinstance(node, dict) else None
        if not isinstance(raw_options, list):
            raise RuntimeError("GitHub Project single-select field omitted options")
        options: list[JsonObject] = []
        for raw in raw_options:
            if not isinstance(raw, dict):
                continue
            option_id = raw.get("id")
            name = raw.get("name")
            color = raw.get("color")
            description = raw.get("description")
            if all(isinstance(value, str) for value in (option_id, name, color, description)):
                options.append(
                    {
                        "id": cast(str, option_id),
                        "name": cast(str, name),
                        "color": cast(str, color),
                        "description": cast(str, description),
                    }
                )
        return options

    def reconcile_project_contract(self) -> JsonObject:
        """Create missing Project fields/options without deleting existing configuration."""
        project = self.project_snapshot()
        configured_url = self._config.project.url
        if configured_url and project.url.rstrip("/") != configured_url.rstrip("/"):
            raise RuntimeError("configured GitHub Project URL does not match project number")

        type_map = {
            "single_select": "SINGLE_SELECT",
            "number": "NUMBER",
            "text": "TEXT",
        }
        create_mutation = """
        mutation($input: CreateProjectV2FieldInput!) {
          createProjectV2Field(input: $input) { clientMutationId }
        }
        """
        update_mutation = """
        mutation($input: UpdateProjectV2FieldInput!) {
          updateProjectV2Field(input: $input) { clientMutationId }
        }
        """
        created_fields: list[str] = []
        added_options: dict[str, list[str]] = {}

        for name, raw_contract in self._config.project.required_fields.items():
            if not isinstance(raw_contract, dict):
                raise RuntimeError(f"invalid Project field contract for {name!r}")
            contract_type = raw_contract.get("type")
            if not isinstance(contract_type, str) or contract_type not in type_map:
                raise RuntimeError(f"unsupported Project field type for {name!r}")
            expected_type = type_map[contract_type]
            raw_options = raw_contract.get("options")
            contract_options: list[str] = []
            if raw_options is not None:
                if not isinstance(raw_options, list) or not all(
                    isinstance(item, str) and item for item in raw_options
                ):
                    raise RuntimeError(f"invalid Project options contract for {name!r}")
                contract_options = cast(list[str], raw_options)

            field = project.fields.get(name)
            if field is None:
                input_value: JsonObject = {
                    "projectId": project.project_id,
                    "dataType": expected_type,
                    "name": name,
                }
                if expected_type == "SINGLE_SELECT":
                    if not contract_options:
                        raise RuntimeError(
                            f"single-select Project field {name!r} requires at least one option"
                        )
                    input_value["singleSelectOptions"] = [
                        {"name": option, "color": "GRAY", "description": ""}
                        for option in contract_options
                    ]
                self._graphql(create_mutation, {"input": input_value})
                created_fields.append(name)
                continue

            if field.data_type != expected_type:
                raise RuntimeError(
                    f"Project field {name!r} has type {field.data_type}, expected {expected_type}; "
                    "bootstrap will not replace an existing field"
                )
            if expected_type != "SINGLE_SELECT" or not contract_options:
                continue

            missing = [option for option in contract_options if option not in field.options]
            if not missing:
                continue
            existing = self._single_select_option_inputs(field.field_id)
            by_name = {cast(str, option["name"]): option for option in existing}
            merged: list[JsonObject] = []
            for option_name in contract_options:
                current = by_name.pop(option_name, None)
                merged.append(
                    current
                    if current is not None
                    else {"name": option_name, "color": "GRAY", "description": ""}
                )
            merged.extend(by_name.values())
            self._graphql(
                update_mutation,
                {"input": {"fieldId": field.field_id, "singleSelectOptions": merged}},
            )
            added_options[name] = missing

        final_project = self.project_snapshot()
        errors = self.verify_project(final_project)
        if errors:
            raise RuntimeError("; ".join(errors))
        return {
            "status": "configured",
            "created_fields": created_fields,
            "added_options": added_options,
        }

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
                for check in raw_checks:
                    if isinstance(check, dict) and isinstance(check.get("context"), str):
                        contexts.add(cast(str, check["context"]))
        missing_checks = set(self._config.branch_policy.required_status_checks) - contexts
        if missing_checks:
            errors.append(
                f"main rules are missing required status checks: {sorted(missing_checks)}"
            )

        ruleset_id = self._config.branch_policy.verified_ruleset_id
        detail = self._rest("GET", f"/repos/{repo}/rulesets/{ruleset_id}")
        if not isinstance(detail, dict) or detail.get("enforcement") != "active":
            errors.append(f"verified ruleset {ruleset_id} is missing or not active")
            return errors
        updated_at = detail.get("updated_at")
        expected_updated_at = self._config.branch_policy.verified_ruleset_updated_at
        if not _same_instant(updated_at, expected_updated_at):
            errors.append(
                "verified ruleset changed after human no-bypass verification; "
                "re-verify it and update branch_policy.verified_ruleset_updated_at"
            )
        bypass = detail.get("bypass_actors")
        if isinstance(bypass, list) and bypass:
            errors.append(f"verified ruleset {ruleset_id} contains bypass actors")
        return errors

    def list_issues(self, *, state: str = "all") -> list[IssueSnapshot]:
        """List repository issues, excluding pull requests, across all pages."""
        repo = self._config.repository.full_name
        result: list[IssueSnapshot] = []
        for page in range(1, 11):
            query = urlencode({"state": state, "per_page": 100, "page": page, "sort": "updated"})
            raw = self._rest("GET", f"/repos/{repo}/issues?{query}")
            if not isinstance(raw, list):
                raise RuntimeError("GitHub issue listing returned invalid data")
            for item in raw:
                if isinstance(item, dict) and "pull_request" not in item:
                    result.append(self._issue(item))
            if len(raw) < 100:
                break
        return result

    def get_issue(self, issue_number: int) -> IssueSnapshot:
        """Read one repository issue."""
        repo = self._config.repository.full_name
        return self._issue(self._rest("GET", f"/repos/{repo}/issues/{issue_number}"))

    def find_issue_by_marker(self, marker: str) -> IssueRef | None:
        """Reconcile an issue by a stable hidden marker before creating a duplicate."""
        for issue in self.list_issues(state="all"):
            if marker in issue.body:
                return issue.ref
        return None

    def create_issue(
        self,
        title: str,
        body: str,
        *,
        labels: list[str] | None = None,
    ) -> IssueRef:
        """Create an issue and return its stable identity."""
        repo = self._config.repository.full_name
        payload: JsonObject = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels
        return self._issue(self._rest("POST", f"/repos/{repo}/issues", payload)).ref

    def update_issue(
        self,
        issue_number: int,
        *,
        title: str | None = None,
        body: str | None = None,
        state: str | None = None,
        state_reason: str | None = None,
    ) -> IssueSnapshot:
        """Patch a managed issue without deleting historical identity."""
        payload: JsonObject = {}
        if title is not None:
            payload["title"] = title
        if body is not None:
            payload["body"] = body
        if state is not None:
            payload["state"] = state
        if state_reason is not None:
            payload["state_reason"] = state_reason
        repo = self._config.repository.full_name
        return self._issue(self._rest("PATCH", f"/repos/{repo}/issues/{issue_number}", payload))

    def list_comments(self, issue_number: int) -> list[IssueComment]:
        """Read every comment on an issue in stable creation order."""
        repo = self._config.repository.full_name
        comments: list[IssueComment] = []
        for page in range(1, 11):
            query = urlencode({"per_page": 100, "page": page})
            raw = self._rest("GET", f"/repos/{repo}/issues/{issue_number}/comments?{query}")
            if not isinstance(raw, list):
                raise RuntimeError("GitHub comments response must be a list")
            for item in raw:
                if not isinstance(item, dict):
                    continue
                comment_id = item.get("id")
                url = item.get("html_url") or item.get("url")
                user = item.get("user")
                author = user.get("login") if isinstance(user, dict) else None
                created_at = item.get("created_at")
                updated_at = item.get("updated_at")
                if all(
                    isinstance(value, expected)
                    for value, expected in (
                        (comment_id, int),
                        (url, str),
                        (author, str),
                        (created_at, str),
                        (updated_at, str),
                    )
                ):
                    comments.append(
                        IssueComment(
                            id=cast(int, comment_id),
                            url=cast(str, url),
                            author=cast(str, author),
                            body=str(item.get("body") or ""),
                            created_at=cast(str, created_at),
                            updated_at=cast(str, updated_at),
                        )
                    )
            if len(raw) < 100:
                break
        return comments

    def find_comment_by_marker(self, issue_number: int, marker: str) -> str | None:
        """Reconcile an audit comment by hidden idempotency marker."""
        for comment in self.list_comments(issue_number):
            if marker in comment.body:
                return comment.url
        return None

    def add_comment(self, issue_number: int, body: str) -> str:
        """Publish an audit/comment response and return its stable API URL."""
        repo = self._config.repository.full_name
        raw = self._rest(
            "POST",
            f"/repos/{repo}/issues/{issue_number}/comments",
            {"body": body},
        )
        url = raw.get("html_url") or raw.get("url") if isinstance(raw, dict) else None
        if not isinstance(url, str):
            raise RuntimeError("GitHub comment creation omitted URL")
        return url

    def list_sub_issues(self, issue_number: int) -> list[IssueSnapshot]:
        """List native GitHub sub-issues in their current priority order."""
        repo = self._config.repository.full_name
        raw = self._rest("GET", f"/repos/{repo}/issues/{issue_number}/sub_issues?per_page=100")
        if not isinstance(raw, list):
            raise RuntimeError("GitHub sub-issues response must be a list")
        return [self._issue(item) for item in raw]

    def add_sub_issue(
        self,
        parent_issue_number: int,
        child_database_id: int,
        *,
        replace_parent: bool = False,
    ) -> None:
        """Attach an existing issue as a native sub-issue."""
        repo = self._config.repository.full_name
        self._rest(
            "POST",
            f"/repos/{repo}/issues/{parent_issue_number}/sub_issues",
            {"sub_issue_id": child_database_id, "replace_parent": replace_parent},
        )

    def remove_sub_issue(self, parent_issue_number: int, child_database_id: int) -> None:
        """Detach a native sub-issue while preserving the child issue."""
        repo = self._config.repository.full_name
        self._rest(
            "DELETE",
            f"/repos/{repo}/issues/{parent_issue_number}/sub_issue",
            {"sub_issue_id": child_database_id},
        )

    def reprioritize_sub_issue(
        self,
        parent_issue_number: int,
        child_database_id: int,
        *,
        after_database_id: int | None = None,
    ) -> None:
        """Move a native sub-issue after another child, or to first when omitted."""
        repo = self._config.repository.full_name
        payload: JsonObject = {"sub_issue_id": child_database_id}
        if after_database_id is not None:
            payload["after_id"] = after_database_id
        else:
            payload["after_id"] = None
        self._rest(
            "PATCH",
            f"/repos/{repo}/issues/{parent_issue_number}/sub_issues/priority",
            payload,
        )

    def list_blockers(self, issue_number: int) -> list[IssueSnapshot]:
        """List issues that currently block an issue."""
        repo = self._config.repository.full_name
        raw = self._rest(
            "GET",
            f"/repos/{repo}/issues/{issue_number}/dependencies/blocked_by?per_page=100",
        )
        if not isinstance(raw, list):
            raise RuntimeError("GitHub dependency response must be a list")
        return [self._issue(item) for item in raw]

    def add_blocker(self, issue_number: int, blocker_database_id: int) -> None:
        """Create a native blocked-by relation."""
        repo = self._config.repository.full_name
        self._rest(
            "POST",
            f"/repos/{repo}/issues/{issue_number}/dependencies/blocked_by",
            {"issue_id": blocker_database_id},
        )

    def remove_blocker(self, issue_number: int, blocker_database_id: int) -> None:
        """Remove one native blocked-by relation."""
        repo = self._config.repository.full_name
        self._rest(
            "DELETE",
            f"/repos/{repo}/issues/{issue_number}/dependencies/blocked_by/{blocker_database_id}",
        )

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

    def find_project_item(self, project: ProjectSnapshot, issue_number: int) -> str | None:
        """Resolve an issue's item id for the configured Project V2."""
        query = """
        query($owner: String!, $name: String!, $number: Int!) {
          repository(owner: $owner, name: $name) {
            issue(number: $number) {
              projectItems(first: 100) { nodes { id project { id } } }
            }
          }
        }
        """
        data = self._graphql(
            query,
            {
                "owner": self._config.repository.owner,
                "name": self._config.repository.name,
                "number": issue_number,
            },
        )
        repository = data.get("repository")
        issue = repository.get("issue") if isinstance(repository, dict) else None
        items = issue.get("projectItems") if isinstance(issue, dict) else None
        nodes = items.get("nodes") if isinstance(items, dict) else None
        if not isinstance(nodes, list):
            return None
        for node in nodes:
            if not isinstance(node, dict):
                continue
            linked_project = node.get("project")
            if (
                isinstance(linked_project, dict)
                and linked_project.get("id") == project.project_id
                and isinstance(node.get("id"), str)
            ):
                return cast(str, node["id"])
        return None

    def ensure_project_item(
        self,
        project: ProjectSnapshot,
        issue: IssueRef | IssueSnapshot,
    ) -> str:
        """Idempotently add an issue to the configured project."""
        number = issue.number
        node_id = issue.node_id
        existing = self.find_project_item(project, number)
        return existing or self.add_to_project(project.project_id, node_id)

    def update_project_fields(
        self,
        project: ProjectSnapshot,
        item_id: str,
        values: dict[str, str | int],
    ) -> None:
        """Set Project V2 fields on a managed work item."""
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

    def find_pull_request_by_head(self, branch: str) -> PullRequestSnapshot | None:
        """Find an existing pull request for one orchestrator-owned branch."""
        repo = self._config.repository.full_name
        head = f"{self._config.repository.owner}:{branch}"
        query = urlencode({"state": "all", "head": head, "per_page": 20})
        raw = self._rest("GET", f"/repos/{repo}/pulls?{query}")
        if not isinstance(raw, list):
            raise RuntimeError("GitHub pull request listing returned invalid data")
        return None if not raw else self._pull_request(raw[0])

    def get_pull_request(self, number: int) -> PullRequestSnapshot:
        """Read one pull request."""
        repo = self._config.repository.full_name
        return self._pull_request(self._rest("GET", f"/repos/{repo}/pulls/{number}"))

    def create_draft_pull_request(
        self,
        *,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> PullRequestSnapshot:
        """Create a draft PR; merge authority remains human-only."""
        repo = self._config.repository.full_name
        raw = self._rest(
            "POST",
            f"/repos/{repo}/pulls",
            {"title": title, "body": body, "head": head, "base": base, "draft": True},
        )
        return self._pull_request(raw)

    def close_pull_request(self, number: int) -> PullRequestSnapshot:
        """Close an orchestrator-owned draft PR without merging it."""
        repo = self._config.repository.full_name
        return self._pull_request(
            self._rest("PATCH", f"/repos/{repo}/pulls/{number}", {"state": "closed"})
        )
