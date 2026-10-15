"""Target Repository Scaffolding Service.

Scaffolds newly created and existing target repositories with:
- CONTEXT.md (domain glossary)
- docs/adr/0001-tanstack-start-spa-architecture.md (baseline architecture ADR)
- docs/agents/ (domain.md, issue-tracker.md, triage-labels.md)
- .agents/skills/ (Matt Pocock engineering skills)
"""

import logging
import os
from pathlib import Path
from time import monotonic, sleep
from typing import Any
import httpx

from factory.ui.github import DEFAULT_TEST_ORG, get_test_org_token, resolve_repo_root, strip_repo_owner

logger = logging.getLogger(__name__)


CONTEXT_TEMPLATE = """# Target Application Domain Context

Single-context frontend application built on TanStack Start with Vite and Tailwind CSS.

## Language

**TanStack Start SPA**:
A modern single-page frontend application powered by TanStack Start router, Vite bundler, and React 19.
_Avoid_: Next.js app, Remix app, Vue app

**Route Tree**:
File-based hierarchical routing defined under `app/routes/` with typed loaders and search parameter validation.
_Avoid_: React router switch, custom router, dynamic route table

**Client State**:
Local and shared component state managed through React state primitives and TanStack Query cache.
_Avoid_: Redux store, MobX store

**Tailwind Styling**:
Utility-first design tokens and responsive classes configured via Tailwind CSS.
_Avoid_: Inline styles, CSS modules, CSS-in-JS

**Architectural Decision Records**:
Historical design records located under `docs/adr/` documenting accepted architectural trade-offs and conventions.
_Avoid_: Architecture notes, design wiki
"""

ADR_0001_TEMPLATE = """# 0001: TanStack Start SPA Architecture

**Status**: Accepted

To provide a resilient, responsive, and type-safe frontend experience, we decided to adopt TanStack Start with Vite and Tailwind CSS as the canonical client architecture for this application.

## Considered Options

- **Server-Side Rendered Framework with Node Backend**: Requires runtime server management, external serverless functions, and heavier deployment footprint. Rejected in favor of lightweight client-first routing.
- **Traditional Create React App / Vanilla Vite**: Lacks typed routing, SSR-ready file-based convention, and modern loader primitives. Rejected because TanStack Start provides robust type safety and route loaders out of the box.
- **TanStack Start with Vite and Tailwind CSS**: Combines modern file-based routing, strict TypeScript validation, type-safe route parameters, fast Vite HMR, and utility-first styling. Accepted as the standard architecture.

## Consequences

- The application uses TanStack Start file-based routing located under `app/routes/`.
- Styling is implemented using Tailwind CSS utility classes.
- All routing and data fetching must use TanStack Start loaders and type-safe navigation.
- Code modifications must preserve file-based route conventions and avoid introducing contradictory routing libraries.
"""

DOMAIN_MD_TEMPLATE = """# Domain Docs

How engineering skills and AI models consume this repository's domain documentation.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root
- **`docs/adr/`**: read all ADRs that touch the area you are about to work in

## File structure

Single-context repo:
- `CONTEXT.md` at repo root
- `docs/adr/` at repo root

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a test name), use the terms defined in `CONTEXT.md`.

## Flag ADR conflicts

If your output contradicts an existing ADR in `docs/adr/`, flag it explicitly. Never silently violate accepted ADRs.
"""

ISSUE_TRACKER_MD_TEMPLATE = """# Issue tracker: GitHub

Issues and specs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`
- **Read an issue**: `gh issue view <number> --comments`
- **List issues**: `gh issue list --state open`
- **Close**: `gh issue close <number> --comment "..."`
"""

TRIAGE_LABELS_MD_TEMPLATE = """# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the actual label strings used in this repo's issue tracker.

| Label in mattpocock/skills | Label in our tracker | Meaning                                  |
| -------------------------- | -------------------- | ---------------------------------------- |
| `needs-triage`             | `needs-triage`       | Maintainer needs to evaluate this issue  |
| `needs-info`               | `needs-info`         | Waiting on reporter for more information |
| `ready-for-agent`          | `ready-for-agent`    | Fully specified, ready for an AFK agent  |
| `ready-for-human`          | `ready-for-human`    | Requires human implementation            |
| `wontfix`                  | `wontfix`            | Will not be actioned                     |
"""

CORE_SKILL_NAMES = [
    "code-review",
    "codebase-design",
    "diagnosing-bugs",
    "domain-modeling",
    "grilling",
    "prototype",
    "tdd",
    "writing-for-agents",
]


class RepoScaffoldingError(Exception):
    """Raised when repository scaffolding fails."""

    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def get_scaffold_files(repo_root: Path | None = None) -> dict[str, str]:
    """Compiles all files and content that must be scaffolded into target repositories."""
    files: dict[str, str] = {
        "CONTEXT.md": CONTEXT_TEMPLATE,
        "docs/adr/0001-tanstack-start-spa-architecture.md": ADR_0001_TEMPLATE,
        "docs/agents/domain.md": DOMAIN_MD_TEMPLATE,
        "docs/agents/issue-tracker.md": ISSUE_TRACKER_MD_TEMPLATE,
        "docs/agents/triage-labels.md": TRIAGE_LABELS_MD_TEMPLATE,
    }

    root = resolve_repo_root(repo_root)
    template_skills_dir = root / "shared" / "target_template_skills"
    agents_skills_dir = root / ".agents" / "skills"

    skills_source_dir = template_skills_dir if template_skills_dir.is_dir() else agents_skills_dir

    if skills_source_dir.is_dir():
        for skill_name in CORE_SKILL_NAMES:
            skill_dir = skills_source_dir / skill_name
            if not skill_dir.is_dir():
                continue
            for cur_dir, _, filenames in os.walk(skill_dir):
                for fname in filenames:
                    file_path = Path(cur_dir) / fname
                    rel_to_skills = file_path.relative_to(skills_source_dir)
                    target_repo_path = f".agents/skills/{rel_to_skills.as_posix()}"
                    try:
                        content = file_path.read_text(encoding="utf-8")
                        files[target_repo_path] = content
                    except Exception:
                        pass

    return files


def scaffold_target_repo(
    repo_name: str,
    token: str | None = None,
    org: str = DEFAULT_TEST_ORG,
    branch: str = "main",
    timeout_secs: float = 20.0,
    poll_interval_secs: float = 1.0,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Scaffolds target repository with skills, domain glossary, and baseline ADR via GitHub API.

    Guarantees Template Provisioning Readiness by polling for the default branch reference
    and base tree SHA before attempting Git tree or commit operations.
    """
    clean_repo = strip_repo_owner(repo_name, org)
    auth_token = token or get_test_org_token(repo_root=repo_root)

    if not auth_token:
        raise RepoScaffoldingError(
            "Missing GitHub organization credentials for scaffolding.",
            status_code=500,
        )

    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SoftwareFactory-Studio/1.0",
    }

    scaffold_files = get_scaffold_files(repo_root=repo_root)
    tree_items = [
        {
            "path": path_str,
            "mode": "100644",
            "type": "blob",
            "content": content_str,
        }
        for path_str, content_str in scaffold_files.items()
    ]

    base_url = f"https://api.github.com/repos/{org}/{clean_repo}"

    try:
        with httpx.Client(timeout=timeout_secs) as client:
            # 1. Poll for Template Provisioning Readiness (commit and base tree on branch)
            commit_sha: str | None = None
            base_tree_sha: str | None = None
            deadline = monotonic() + timeout_secs
            poll_count = 0

            while True:
                poll_count += 1
                ref_resp = client.get(f"{base_url}/git/ref/heads/{branch}", headers=headers)
                if ref_resp.status_code == 200:
                    commit_sha = ref_resp.json().get("object", {}).get("sha")
                    if commit_sha:
                        commit_resp = client.get(f"{base_url}/git/commits/{commit_sha}", headers=headers)
                        if commit_resp.status_code == 200:
                            base_tree_sha = commit_resp.json().get("tree", {}).get("sha")
                            if base_tree_sha:
                                logger.info(
                                    "Template Provisioning Readiness established for %s/%s (branch: %s, commit: %s, base_tree: %s) after %d poll(s)",
                                    org, clean_repo, branch, commit_sha, base_tree_sha, poll_count,
                                )
                                break
                elif ref_resp.status_code not in (404, 409):
                    raise RepoScaffoldingError(
                        f"Failed to check branch reference '{branch}' ({ref_resp.status_code}): {ref_resp.text}",
                        status_code=ref_resp.status_code,
                    )

                time_remaining = deadline - monotonic()
                if time_remaining <= 0:
                    break

                logger.info(
                    "Waiting for Template Provisioning Readiness on %s/%s (branch: %s, attempt %d)...",
                    org, clean_repo, branch, poll_count,
                )
                sleep_secs = min(poll_interval_secs, time_remaining)
                sleep(sleep_secs)

            if not commit_sha or not base_tree_sha:
                raise RepoScaffoldingError(
                    f"Timed out waiting for repository template replication on '{org}/{clean_repo}' after {timeout_secs:.1f}s. "
                    "Template Provisioning Readiness was not established (default branch reference or base tree SHA unavailable).",
                    status_code=504,
                )

            # 2. Create new tree
            tree_payload: dict[str, Any] = {
                "tree": tree_items,
                "base_tree": base_tree_sha,
            }

            tree_resp = client.post(f"{base_url}/git/trees", headers=headers, json=tree_payload)
            if tree_resp.status_code not in (200, 201):
                raise RepoScaffoldingError(
                    f"Failed to create Git tree ({tree_resp.status_code}): {tree_resp.text}",
                    status_code=tree_resp.status_code,
                )
            new_tree_sha = tree_resp.json()["sha"]

            # 3. Create commit
            commit_payload: dict[str, Any] = {
                "message": "Scaffold target repository with engineering skills, domain docs, and baseline ADR",
                "tree": new_tree_sha,
                "parents": [commit_sha],
            }
            new_commit_resp = client.post(f"{base_url}/git/commits", headers=headers, json=commit_payload)
            if new_commit_resp.status_code not in (200, 201):
                raise RepoScaffoldingError(
                    f"Failed to create Git commit ({new_commit_resp.status_code}): {new_commit_resp.text}",
                    status_code=new_commit_resp.status_code,
                )
            new_commit_sha = new_commit_resp.json()["sha"]

            # 4. Update branch ref
            ref_update_resp = client.patch(
                f"{base_url}/git/refs/heads/{branch}",
                headers=headers,
                json={"sha": new_commit_sha, "force": False},
            )
            if ref_update_resp.status_code not in (200, 201):
                raise RepoScaffoldingError(
                    f"Failed to update branch ref ({ref_update_resp.status_code}): {ref_update_resp.text}",
                    status_code=ref_update_resp.status_code,
                )

            return {
                "repo": clean_repo,
                "org": org,
                "branch": branch,
                "commit_sha": new_commit_sha,
                "files_count": len(scaffold_files),
                "status": "scaffolded",
            }
    except RepoScaffoldingError:
        raise
    except Exception as e:
        raise RepoScaffoldingError(
            f"Error scaffolding target repository '{clean_repo}': {e}",
            status_code=502,
        )
