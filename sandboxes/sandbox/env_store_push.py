"""Central Environment Store push and secret encryption logic.

Handles encrypting local environment secrets with SOPS using recipient Age keys,
committing encrypted payloads to github.com/${GH_ORG_NAME}/env-store using the
GitHub Contents REST API, and managing the env.map mapping manifest.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any
import urllib.error
import urllib.request

from sandbox.env_store import (
    DEFAULT_VAULT_REPO,
    SOPS_SUPPORTED_EXTENSIONS,
    detect_repo_name,
    fetch_github_file,
    get_file_extension,
    is_sops_supported_format,
    resolve_gh_token,
    update_env_map_content,
)


DEFAULT_AGE_RECIPIENT = "age1zwr6flwyk3lt6k0xsd9wy0qy4dlytkdyv5aggvqu6zxqt3p2eyrsw5n4qj"


@dataclass
class PushResult:
    """Outcome of an env-store push operation."""
    success: bool
    repo_name: str
    target_path: str
    commit_sha: str | None = None
    message: str = ""
    org_name: str | None = None


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
    """Commits or updates a file in env-store using GitHub Contents REST API."""
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

    msg = commit_message or f"chore({path.split('/')[0]}): update {path.split('/')[-1]}"
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


def push_repo_env(
    repo_dir: Path,
    env_file: Path | None = None,
    repo_name: str | None = None,
    org_name: str | None = None,
    gh_token: str | None = None,
    recipient: str | None = None,
    dest_name: str | None = None,
    vault_repo: str = DEFAULT_VAULT_REPO,
    allow_binary: bool = False,
    encrypt_fn: Any = None,
    commit_fn: Any = None,
    fetch_fn: Any = None,
) -> PushResult:
    """Encrypts local .env, commits to env-store vault, and automatically updates env.map."""
    src = env_file or (repo_dir / ".env")
    if not src.is_file():
        return PushResult(False, repo_name or "", "", message=f"Source .env file not found: {src}")
    if not dest_name:
        if src.name == ".env":
            dest_name = "default.env"
        else:
            return PushResult(
                False,
                repo_name or "",
                "",
                message=(
                    f"When source environment file is not '.env' ('{src.name}'), you must also pass -d/--dest "
                    "to define the destination in env-store."
                ),
            )

    det_org, det_name = detect_repo_name(repo_dir)
    final_repo = repo_name or det_name
    final_org = org_name or det_org or os.environ.get("GH_ORG_NAME") or os.environ.get("GH_ORG")
    token = resolve_gh_token(gh_token)
    recip = recipient or DEFAULT_AGE_RECIPIENT

    if not final_org:
        return PushResult(False, final_repo, "", message="GitHub organization not found. Please set GH_ORG_NAME or pass -o <org>.")
    if not token:
        return PushResult(False, final_repo, "", message="GitHub token not found. Please set GH_TOKEN or GITHUB_TOKEN, log in via 'gh auth login', or pass -t/--token.")

    if not is_sops_supported_format(dest_name) and not allow_binary:
        ext = get_file_extension(dest_name) or "(no extension)"
        valid = ", ".join(sorted(SOPS_SUPPORTED_EXTENSIONS))
        return PushResult(
            False,
            final_repo,
            "",
            message=f"Destination file '{dest_name}' has unsupported extension '{ext}'. Supported formats: {valid}. Pass --allow-binary to allow encrypting arbitrary or binary files.",
        )

    ensure_gitignore(repo_dir)
    vault_path = f"{final_repo}/{dest_name}"
    sha = _encrypt_and_commit(src, final_org, vault_repo, vault_path, token, recip, encrypt_fn=encrypt_fn, commit_fn=commit_fn, filename_override=dest_name)

    # Maintain env.map manifest in env-store
    fetch_f = fetch_fn or fetch_github_file
    com_f = commit_fn or commit_to_env_store
    map_path = f"{final_repo}/env.map"
    raw_map = fetch_f(final_org, vault_repo, map_path, token=token)

    try:
        rel_dest = str(src.resolve().relative_to(repo_dir.resolve()))
    except ValueError:
        rel_dest = src.name

    new_map = update_env_map_content(raw_map, dest_name, rel_dest)
    if raw_map is None and dest_name != "default.env":
        if fetch_f(final_org, vault_repo, f"{final_repo}/default.env", token=token):
            new_map = update_env_map_content(new_map, "default.env", ".env")

    if new_map != (raw_map or ""):
        com_f(
            owner=final_org,
            env_repo=vault_repo,
            path=map_path,
            content_bytes=new_map.encode("utf-8"),
            token=token,
            commit_message=f"chore({final_repo}): update env.map manifest",
        )

    return PushResult(True, final_repo, vault_path, commit_sha=sha, message="Pushed successfully.", org_name=final_org)


def push_repo_git_identity(
    repo_dir: Path,
    name: str | None = None,
    email: str | None = None,
    repo_name: str | None = None,
    org_name: str | None = None,
    gh_token: str | None = None,
    recipient: str | None = None,
    vault_repo: str = DEFAULT_VAULT_REPO,
    encrypt_fn: Any = None,
    commit_fn: Any = None,
) -> PushResult:
    """Encrypts repository-specific Git authorship and commits to <repo>/git.env in env-store."""
    det_org, det_name = detect_repo_name(repo_dir)
    final_repo = repo_name or det_name
    final_org = org_name or det_org or os.environ.get("GH_ORG_NAME") or os.environ.get("GH_ORG")
    token = resolve_gh_token(gh_token)
    recip = recipient or DEFAULT_AGE_RECIPIENT

    if not final_org:
        return PushResult(False, final_repo, "", message="GitHub organization not found. Please set GH_ORG_NAME or pass -o <org>.")
    if not token:
        return PushResult(False, final_repo, "", message="GitHub token not found. Please set GH_TOKEN or GITHUB_TOKEN, log in via 'gh auth login', or pass -t/--token.")

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
        vault_path = f"{final_repo}/git.env"
        sha = _encrypt_and_commit(
            tmp_src_path,
            final_org,
            vault_repo,
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
