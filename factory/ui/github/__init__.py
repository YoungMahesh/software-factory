"""GitHub Discovery and Management Package for Canonical Test Organization.

Re-exports all public functions, classes, and constants for full backward compatibility.
"""

from factory.ui.github._branches import (
    check_tanstack_start_compatibility,
    commit_approved_adr_to_branch,
    fetch_repo_branches,
    fetch_repo_branches_with_diagnostics,
    fetch_repo_scratch_metadata,
    fetch_test_org_repos,
    fetch_test_org_repos_detailed,
    instantiate_repo_from_template,
)
from factory.ui.github._client import (
    DEFAULT_TEST_ORG,
    FALLBACK_REPOS,
    get_test_org_token,
    resolve_repo_root,
    strip_repo_owner,
)
from factory.ui.github._issues import (
    _normalize_github_issue,
    create_repo_issue,
    create_repo_milestone,
    fetch_repo_issue,
    fetch_repo_issues,
    fetch_repo_milestones,
    fetch_repo_milestones_and_issues,
    map_github_issue_status,
    normalize_milestone_slug,
    parse_github_blocked_by,
    resolve_or_create_milestone,
    synthesize_and_create_issue,
    synthesize_ticket_content,
)
from factory.ui.github._models import (
    CANONICAL_TEMPLATE_ORG,
    CANONICAL_TEMPLATE_REPO,
    FACTORY_LABELS,
    REPO_NAME_REGEX,
    PullRequestMergeError,
    RepoCreationError,
    validate_github_repo_name,
)
from factory.ui.github._prs import (
    _normalize_github_pull_request,
    fetch_repo_pull_requests,
    merge_repo_pull_request,
)
from factory.ui.github._rollback import (
    reopen_repo_issue_for_rollback,
)
from factory.ui.tracker import (
    update_local_markdown_issue_for_rollback,
)

__all__ = [
    "CANONICAL_TEMPLATE_ORG",
    "CANONICAL_TEMPLATE_REPO",
    "DEFAULT_TEST_ORG",
    "FACTORY_LABELS",
    "FALLBACK_REPOS",
    "PullRequestMergeError",
    "REPO_NAME_REGEX",
    "RepoCreationError",
    "_normalize_github_issue",
    "_normalize_github_pull_request",
    "check_tanstack_start_compatibility",
    "commit_approved_adr_to_branch",
    "create_repo_issue",
    "create_repo_milestone",
    "fetch_repo_branches",
    "fetch_repo_branches_with_diagnostics",
    "fetch_repo_issue",
    "fetch_repo_issues",
    "fetch_repo_milestones",
    "fetch_repo_milestones_and_issues",
    "fetch_repo_pull_requests",
    "fetch_repo_scratch_metadata",
    "fetch_test_org_repos",
    "fetch_test_org_repos_detailed",
    "get_test_org_token",
    "instantiate_repo_from_template",
    "map_github_issue_status",
    "merge_repo_pull_request",
    "normalize_milestone_slug",
    "parse_github_blocked_by",
    "reopen_repo_issue_for_rollback",
    "resolve_or_create_milestone",
    "resolve_repo_root",
    "strip_repo_owner",
    "synthesize_and_create_issue",
    "synthesize_ticket_content",
    "update_local_markdown_issue_for_rollback",
    "validate_github_repo_name",
]
