"""Host Git identity and software-factory repository provenance resolution."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess


def resolve_host_git_identity(repo_root: Path | None = None) -> dict[str, str]:
    """Dynamically resolves host Git identity from environment, .env file, or git configuration."""
    git_env: dict[str, str] = {}
    name = (
        os.environ.get("GIT_AUTHOR_NAME")
        or os.environ.get("GIT_COMMITTER_NAME")
        or os.environ.get("DEFAULT_GIT_NAME")
    )
    email = (
        os.environ.get("GIT_AUTHOR_EMAIL")
        or os.environ.get("GIT_COMMITTER_EMAIL")
        or os.environ.get("DEFAULT_GIT_EMAIL")
    )

    if not name or not email:
        if repo_root:
            dotenv_paths = [repo_root / ".env"]
        else:
            dotenv_paths = [Path("/root/.env"), Path.cwd() / ".env"], Path(__file__).resolve().parent.parent / ".env"
        for p in dotenv_paths:
            if isinstance(p, Path) and p.is_file():
                try:
                    for line in p.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip("'\"")
                        if not name and k in ("DEFAULT_GIT_NAME", "GIT_AUTHOR_NAME"):
                            name = v
                        if not email and k in ("DEFAULT_GIT_EMAIL", "GIT_AUTHOR_EMAIL"):
                            email = v
                except Exception:
                    pass
                if name and email:
                    break

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
        git_env["DEFAULT_GIT_NAME"] = name
    if email:
        git_env["GIT_AUTHOR_EMAIL"] = email
        git_env["GIT_COMMITTER_EMAIL"] = email
        git_env["DEFAULT_GIT_EMAIL"] = email
    return git_env


def resolve_host_software_factory_provenance(repo_root: Path | None = None) -> dict[str, str]:
    """Dynamically resolves software-factory Git provenance and dirty state.

    Hierarchy:
    1. If SOFTWARE_FACTORY_FORCE_ENV == "1", explicitly respect process environment variables.
    2. If target directory contains a valid Git repository ((target_dir / ".git").exists()),
       inspect Git directly (git rev-parse HEAD, git symbolic-ref, git status --porcelain).
    3. Fall back to process environment variables (e.g. inside deployed Modal cloud containers).
    4. Fall back to "unknown" sentinels if neither Git nor environment variables are available.
    """
    target_dir = repo_root or Path(__file__).resolve().parent.parent
    force_env = os.environ.get("SOFTWARE_FACTORY_FORCE_ENV") == "1"

    commit = ""
    commit_short = ""
    ref = ""
    dirty = ""

    # 1. Explicit force environment override (for CI or mocked fixtures)
    if force_env:
        commit = os.environ.get("SOFTWARE_FACTORY_COMMIT", "").strip()
        commit_short = os.environ.get("SOFTWARE_FACTORY_COMMIT_SHORT", "").strip()
        ref = os.environ.get("SOFTWARE_FACTORY_REF", "").strip()
        dirty = os.environ.get("SOFTWARE_FACTORY_DIRTY", "").strip()
        if commit == "unknown":
            commit = ""
        if commit_short == "unknown":
            commit_short = ""
        if ref == "unknown":
            ref = ""

    # 2. Live Git inspection when a .git repository/worktree exists
    if not force_env and (target_dir / ".git").exists():
        try:
            res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=target_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                commit = res.stdout.strip()

            res_short = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=target_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            if res_short.returncode == 0 and res_short.stdout.strip():
                commit_short = res_short.stdout.strip()
            elif commit and len(commit) >= 7:
                commit_short = commit[:7]

            res_ref = subprocess.run(
                ["git", "symbolic-ref", "--short", "HEAD"],
                cwd=target_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            if res_ref.returncode == 0 and res_ref.stdout.strip():
                ref = res_ref.stdout.strip()
            else:
                res_ref2 = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=target_dir,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if res_ref2.returncode == 0 and res_ref2.stdout.strip():
                    ref = res_ref2.stdout.strip()

            res_status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=target_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            if res_status.returncode == 0:
                dirty = "1" if res_status.stdout.strip() else "0"
        except Exception:
            pass

    # 3. Fallback to process environment variables (cloud container or missing .git)
    if not commit:
        env_commit = os.environ.get("SOFTWARE_FACTORY_COMMIT", "").strip()
        if env_commit and env_commit != "unknown":
            commit = env_commit
    if not commit_short:
        env_short = os.environ.get("SOFTWARE_FACTORY_COMMIT_SHORT", "").strip()
        if env_short and env_short != "unknown":
            commit_short = env_short
        elif commit and commit != "unknown" and len(commit) >= 7:
            commit_short = commit[:7]
    if not ref:
        env_ref = os.environ.get("SOFTWARE_FACTORY_REF", "").strip()
        if env_ref and env_ref != "unknown":
            ref = env_ref
    if not dirty:
        env_dirty = os.environ.get("SOFTWARE_FACTORY_DIRTY", "").strip()
        if env_dirty:
            dirty = env_dirty

    return {
        "SOFTWARE_FACTORY_COMMIT": commit or "unknown",
        "SOFTWARE_FACTORY_COMMIT_SHORT": commit_short or (commit[:7] if commit and commit != "unknown" else "unknown"),
        "SOFTWARE_FACTORY_REF": ref or "unknown",
        "SOFTWARE_FACTORY_DIRTY": dirty or "0",
    }
