"""Host Git identity and software-factory repository provenance resolution."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess


def resolve_host_git_identity() -> dict[str, str]:
    """Dynamically resolves host Git identity from environment or git configuration."""
    git_env: dict[str, str] = {}
    name = os.environ.get("GIT_AUTHOR_NAME") or os.environ.get("GIT_COMMITTER_NAME")
    email = os.environ.get("GIT_AUTHOR_EMAIL") or os.environ.get("GIT_COMMITTER_EMAIL")
    if not name:
        try:
            res = subprocess.run(
                ["git", "config", "user.name"],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                name = res.stdout.strip()
        except Exception:
            pass
    if not email:
        try:
            res = subprocess.run(
                ["git", "config", "user.email"],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                email = res.stdout.strip()
        except Exception:
            pass

    if name:
        git_env["GIT_AUTHOR_NAME"] = name
        git_env["GIT_COMMITTER_NAME"] = name
    if email:
        git_env["GIT_AUTHOR_EMAIL"] = email
        git_env["GIT_COMMITTER_EMAIL"] = email
    return git_env


def resolve_host_software_factory_provenance(repo_root: Path | None = None) -> dict[str, str]:
    """Dynamically resolves software-factory Git provenance and dirty state."""
    commit = os.environ.get("SOFTWARE_FACTORY_COMMIT", "").strip()
    commit_short = os.environ.get("SOFTWARE_FACTORY_COMMIT_SHORT", "").strip()
    ref = os.environ.get("SOFTWARE_FACTORY_REF", "").strip()
    dirty = os.environ.get("SOFTWARE_FACTORY_DIRTY", "").strip()

    target_dir = repo_root or Path(__file__).resolve().parent.parent

    if not commit or not ref or not dirty:
        try:
            if not commit:
                res = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=target_dir,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if res.returncode == 0 and res.stdout.strip():
                    commit = res.stdout.strip()

            if not commit_short:
                if commit and commit != "unknown" and len(commit) >= 7:
                    commit_short = commit[:7]
                else:
                    res = subprocess.run(
                        ["git", "rev-parse", "--short", "HEAD"],
                        cwd=target_dir,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if res.returncode == 0 and res.stdout.strip():
                        commit_short = res.stdout.strip()

            if not ref:
                res = subprocess.run(
                    ["git", "symbolic-ref", "--short", "HEAD"],
                    cwd=target_dir,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if res.returncode == 0 and res.stdout.strip():
                    ref = res.stdout.strip()
                else:
                    res2 = subprocess.run(
                        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                        cwd=target_dir,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if res2.returncode == 0 and res2.stdout.strip():
                        ref = res2.stdout.strip()

            if not dirty:
                res = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=target_dir,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if res.returncode == 0:
                    dirty = "1" if bool(res.stdout.strip()) else "0"
        except Exception:
            pass

    if not commit:
        commit = "unknown"
    if not commit_short:
        commit_short = commit[:7] if commit != "unknown" else "unknown"
    if not ref:
        ref = "unknown"
    if not dirty:
        dirty = "0"

    return {
        "SOFTWARE_FACTORY_COMMIT": commit,
        "SOFTWARE_FACTORY_COMMIT_SHORT": commit_short,
        "SOFTWARE_FACTORY_REF": ref,
        "SOFTWARE_FACTORY_DIRTY": dirty,
    }
