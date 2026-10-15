"""Data models, validation rules, regexes, and domain exceptions for GitHub operations."""

import re

FACTORY_LABELS = {
    "READY": "factory:ready",
    "CLAIMED": "factory:claimed",
    "RESOLVED": "factory:resolved",
    "READY_FOR_HUMAN": "factory:ready-for-human",
}

CANONICAL_TEMPLATE_ORG = "software-factory-09-test"
CANONICAL_TEMPLATE_REPO = "tanstack-start-template"

REPO_NAME_REGEX = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")


def validate_github_repo_name(name: str) -> tuple[bool, str | None]:
    """Validates that a repository name complies with GitHub repository slug requirements."""
    if not isinstance(name, str) or not name.strip():
        return False, "Repository name cannot be empty."

    trimmed = name.strip()
    if len(trimmed) > 100:
        return False, "Repository name cannot exceed 100 characters."

    if trimmed in (".", "..") or trimmed.lower() == ".git" or trimmed.lower().endswith(".git"):
        return False, "Repository name cannot be '.', '..', or end with '.git'."

    if not REPO_NAME_REGEX.match(trimmed):
        return False, (
            "Repository name must start with an alphanumeric character and contain "
            "only alphanumeric characters, hyphens, underscores, or periods."
        )

    return True, None


class RepoCreationError(Exception):
    """Raised when repository instantiation fails."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class PullRequestMergeError(Exception):
    """Raised when a pull request merge operation fails."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
