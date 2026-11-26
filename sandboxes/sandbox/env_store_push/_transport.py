"""Transport, SOPS encryption, GitHub commit, and Git identity helpers for Central Config Store."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any
import urllib.error
import urllib.request

DEFAULT_AGE_RECIPIENT = "age1zwr6flwyk3lt6k0xsd9wy0qy4dlytkdyv5aggvqu6zxqt3p2eyrsw5n4qj"


class NonInteractivePromptError(RuntimeError):
    """Raised when interactive confirmation is required on a non-TTY stdin."""


@dataclass
class PushFileOutcome:
    """Outcome for an individual file within an env-store push operation."""

    vault_name: str
    rel_path: str
    target_path: str
    success: bool
    commit_sha: str | None = None
    message: str = ""


@dataclass
class PushResult:
    """Outcome of an env-store push operation."""

    success: bool
    repo_name: str
    target_path: str
    commit_sha: str | None = None
    message: str = ""
    org_name: str | None = None
    pushed_files: list[PushFileOutcome] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)
    failed_files: list[PushFileOutcome] = field(default_factory=list)
    declined_all: bool = False


def ensure_gitignore(repo_dir: Path) -> bool:
    """Ensures .gitignore in the target repository ignores .env files."""
    gitignore = repo_dir / ".gitignore"
    if not gitignore.is_file():
        gitignore.write_text(".env*\n", encoding="utf-8")
        return True
    content = gitignore.read_text(encoding="utf-8")
    if any(p in (".env", ".env*", ".env.*") for p in [line.strip() for line in content.splitlines()]):
        return False
    with open(gitignore, "a", encoding="utf-8") as f:
        f.write(("" if content.endswith("\n") or not content else "\n") + ".env*\n")
    return True


def run_sops_encrypt(
    src_file: Path,
    dest_file: Path,
    recipient: str,
    filename_override: str | None = None,
) -> None:
    """Encrypts src_file with SOPS using recipient Age key."""
    if not shutil.which("sops"):
        raise RuntimeError("sops executable not found in PATH.")
    cmd = ["sops", "--encrypt"]
    if filename_override:
        cmd.extend(["--filename-override", filename_override])
    cmd.extend(["--age", recipient, str(src_file)])
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"SOPS encryption failed: {res.stderr.strip()}")
    dest_file.write_text(res.stdout, encoding="utf-8")


def commit_to_env_store(
    owner: str,
    env_repo: str,
    path: str,
    content_bytes: bytes,
    token: str,
    commit_message: str | None = None,
) -> str:
    """Commits or updates a file in Central Config Store using GitHub Contents REST API."""
    url = f"https://api.github.com/repos/{owner}/{env_repo}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "push-repo-env",
    }
    sha = None
    try:
        req_get = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req_get) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict) and "sha" in data:
                sha = data["sha"]
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise

    parts = [p for p in path.strip("/").split("/") if p]
    scope = parts[1] if len(parts) >= 3 and parts[0] in ("env", "caddy") else (parts[0] if parts else "config")
    filename = parts[-1] if parts else path
    msg = commit_message or f"chore({scope}): update {filename}"
    body: dict[str, str] = {
        "message": msg,
        "content": base64.b64encode(content_bytes).decode("ascii"),
    }
    if sha:
        body["sha"] = sha

    req_put = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="PUT",
    )
    with urllib.request.urlopen(req_put) as put_resp:
        return json.loads(put_resp.read().decode("utf-8")).get("commit", {}).get("sha", "ok")


def _encrypt_and_commit(
    src_path: Path,
    owner: str,
    vault_repo: str,
    vault_path: str,
    token: str,
    recipient: str,
    commit_msg: str | None = None,
    encrypt_fn: Any = None,
    commit_fn: Any = None,
    filename_override: str | None = None,
) -> str:
    enc = encrypt_fn or run_sops_encrypt
    com = commit_fn or commit_to_env_store
    with tempfile.NamedTemporaryFile("w+", suffix=".env", delete=False) as tmp_enc:
        tmp_enc_path = Path(tmp_enc.name)
    try:
        try:
            enc(src_path, tmp_enc_path, recipient, filename_override=filename_override)
        except TypeError:
            enc(src_path, tmp_enc_path, recipient)
        return com(
            owner=owner,
            env_repo=vault_repo,
            path=vault_path,
            content_bytes=tmp_enc_path.read_bytes(),
            token=token,
            commit_message=commit_msg,
        )
    finally:
        if tmp_enc_path.is_file():
            tmp_enc_path.unlink()


def _resolve_repo_context(
    repo_dir: Path,
    repo_name: str | None,
    org_name: str | None,
    gh_token: str | None,
    recipient: str | None,
) -> tuple[str, str | None, str | None, str, str | None]:
    """Resolves repo, org, GitHub token, and Age recipient, returning optional error message."""
    from sandbox.env_store import detect_repo_name, resolve_gh_token

    det_org, det_name = detect_repo_name(repo_dir)
    final_repo = repo_name or det_name
    final_org = org_name or det_org or os.environ.get("GH_ORG_NAME") or os.environ.get("GH_ORG")
    token = resolve_gh_token(gh_token)
    recip = recipient or DEFAULT_AGE_RECIPIENT
    if not final_org:
        return final_repo, None, token, recip, "GitHub organization not found. Please set GH_ORG_NAME or pass -o <org>."
    if not token:
        return final_repo, final_org, None, recip, "GitHub token not found. Please set GH_TOKEN or GITHUB_TOKEN, log in via 'gh auth login', or pass -t/--token."
    return final_repo, final_org, token, recip, None


def push_repo_git_identity(
    repo_dir: Path,
    name: str | None = None,
    email: str | None = None,
    repo_name: str | None = None,
    org_name: str | None = None,
    gh_token: str | None = None,
    recipient: str | None = None,
    vault_repo: str | None = None,
    encrypt_fn: Any = None,
    commit_fn: Any = None,
) -> PushResult:
    """Encrypts repository-specific Git authorship and commits to env/<repo>/git.env in Central Config Store."""
    from sandbox.env_store import DEFAULT_VAULT_REPO, ENV_STORE_PREFIX

    target_vault_repo = vault_repo or DEFAULT_VAULT_REPO
    final_repo, final_org, token, recip, err = _resolve_repo_context(repo_dir, repo_name, org_name, gh_token, recipient)
    if err or not final_org or not token:
        return PushResult(False, final_repo, "", message=err or "Missing repository credentials.")

    final_name = name or os.environ.get("GIT_AUTHOR_NAME")
    final_email = email or os.environ.get("GIT_AUTHOR_EMAIL")
    if not final_name or not final_email:
        for cmd, attr in [("user.name", "final_name"), ("user.email", "final_email")]:
            if not locals()[attr]:
                res = subprocess.run(["git", "-C", str(repo_dir), "config", cmd], capture_output=True, text=True, check=False)
                if res.returncode == 0 and res.stdout.strip():
                    if attr == "final_name":
                        final_name = res.stdout.strip()
                    if attr == "final_email":
                        final_email = res.stdout.strip()

    if not final_name or not final_email:
        return PushResult(False, final_repo, "", message="Git author name and email are required. Provide --name and --email, or configure git user.name and user.email.")

    raw_env_content = f"GIT_AUTHOR_NAME='{final_name}'\nGIT_AUTHOR_EMAIL='{final_email}'\n"
    with tempfile.NamedTemporaryFile("w+", suffix=".env", delete=False) as tmp_src:
        tmp_src.write(raw_env_content)
        tmp_src_path = Path(tmp_src.name)
    try:
        vault_path = f"{ENV_STORE_PREFIX}/{final_repo}/git.env"
        sha = _encrypt_and_commit(
            tmp_src_path,
            final_org,
            target_vault_repo,
            vault_path,
            token,
            recip,
            commit_msg=f"chore({final_repo}): update git.env authorship",
            encrypt_fn=encrypt_fn,
            commit_fn=commit_fn,
        )
        return PushResult(True, final_repo, vault_path, commit_sha=sha, message="Pushed git authorship successfully.", org_name=final_org)
    finally:
        if tmp_src_path.is_file():
            tmp_src_path.unlink()
