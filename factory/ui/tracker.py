"""Local Markdown Issue Tracker synchronization for Factory Studio.

Handles local filesystem ticket updates under .scratch/<feature>/issues/ for target projects.
"""

from pathlib import Path
import re


def update_local_markdown_issue_for_rollback(
    repo_name: str,
    feature: str | None = None,
    issue_number: int | str | None = None,
    repo_root: Path | None = None,
) -> bool:
    """Updates local markdown issue file under .scratch/<feature>/issues/ to ready-for-agent and strips commit line."""
    if issue_number is None:
        return False

    clean_repo = repo_name.strip().split("/")[-1]
    if repo_root is not None:
        search_dirs = [repo_root]
    else:
        search_dirs = [Path.cwd() / "projects" / clean_repo]

    updated = False

    for base_dir in search_dirs:
        scratch_dir = base_dir / ".scratch"
        if not scratch_dir.is_dir():
            continue

        feature_dirs = [scratch_dir / feature] if feature and (scratch_dir / feature).is_dir() else list(scratch_dir.iterdir())
        for fdir in feature_dirs:
            if not fdir.is_dir():
                continue
            issues_dir = fdir / "issues"
            if not issues_dir.is_dir():
                continue

            for issue_file in issues_dir.glob("*.md"):
                prefix = f"{int(issue_number):02d}-" if str(issue_number).isdigit() else f"{issue_number}-"
                alt_prefix = f"{issue_number}-"
                if not (issue_file.name.startswith(prefix) or issue_file.name.startswith(alt_prefix) or issue_file.stem == str(issue_number)):
                    continue

                try:
                    content = issue_file.read_text(encoding="utf-8")
                    new_content = re.sub(
                        r"(?i)(\*{0,2}Status(?::\*{0,2}|\*{0,2}:)\s*)\S+",
                        r"\g<1>ready-for-agent",
                        content,
                    )
                    new_content = re.sub(
                        r"(?i)\n\s*\*{0,2}Commit(?::\*{0,2}|\*{0,2}:)\s*[^\n]+",
                        "",
                        new_content,
                    )
                    if new_content != content:
                        issue_file.write_text(new_content, encoding="utf-8")
                        updated = True
                except Exception:
                    pass
    return updated
