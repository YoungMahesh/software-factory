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
        dotenv_paths: list[Path] = []
        if repo_root:
            dotenv_paths.append(repo_root / ".env")
        dotenv_paths.extend([Path("/root/.env"), Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"])
        for p in dotenv_paths:
            if p.is_file():
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
                    dirty = "1" if res.stdout.strip() else "0"
        except Exception:
            pass

    return {
        "SOFTWARE_FACTORY_COMMIT": commit or "unknown",
        "SOFTWARE_FACTORY_COMMIT_SHORT": commit_short or (commit[:7] if commit and commit != "unknown" else "unknown"),
        "SOFTWARE_FACTORY_REF": ref or "unknown",
        "SOFTWARE_FACTORY_DIRTY": dirty or "0",
    }
