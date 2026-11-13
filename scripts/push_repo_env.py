#!/usr/bin/env python3
"""Push local project environment secrets to the Central Environment Store (env-store).

Encrypts a project's .env using the organization's public Age recipient key and
commits it directly to github.com/${GH_ORG_NAME}/env-store via GitHub REST API
as defined in ADR 0096.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

# Ensure repository root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from sandbox.env_store import resolve_gh_token

DEFAULT_AGE_RECIPIENT = "age1zwr6flwyk3lt6k0xsd9wy0qy4dlytkdyv5aggvqu6zxqt3p2eyrsw5n4qj"
DEFAULT_KEY_FILE = Path.home() / ".config" / "sops" / "age" / "keys.txt"
DEFAULT_VAULT_REPO = "env-store"


@dataclass
class PushResult:
    success: bool
    repo_name: str
    target_path: str
    commit_sha: str | None = None
    message: str = ""
    org_name: str | None = None


def ensure_gitignore(repo_dir: Path) -> bool:
    """Ensures .gitignore in the target repository ignores .env files."""
    gitignore = repo_dir / ".gitignore"
    entry = ".env*\n"

    if not gitignore.is_file():
        gitignore.write_text(entry, encoding="utf-8")
        return True

    content = gitignore.read_text(encoding="utf-8")
    patterns = [line.strip() for line in content.splitlines()]
    if any(p in (".env", ".env*", ".env.*") for p in patterns):
        return False

    with open(gitignore, "a", encoding="utf-8") as f:
        if content and not content.endswith("\n"):
            f.write("\n")
        f.write(entry)
    return True


def detect_repo_name(repo_dir: Path) -> tuple[str | None, str]:
    """Detects GitHub owner and repository name from git remote origin."""
    try:
        res = subprocess.run(
            ["git", "-C", str(repo_dir), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            url = res.stdout.strip()
            # Handle ssh (git@github.com:owner/repo.git) or https (https://github.com/owner/repo.git)
            match = re.search(r"github\.com[:/]([^/]+)/([^/\.]+)(?:\.git)?$", url)
            if match:
                return match.group(1), match.group(2)
    except Exception:
        pass
    return None, repo_dir.resolve().name


def run_sops_encrypt(src_file: Path, dest_file: Path, recipient: str) -> None:
    """Encrypts src_file with SOPS using recipient Age key."""
    if not shutil.which("sops"):
        raise RuntimeError("sops executable not found in PATH.")

    cmd = [
        "sops",
        "--encrypt",
        "--age",
        recipient,
        str(src_file),
    ]
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
        res_data = json.loads(put_resp.read().decode("utf-8"))
        return res_data.get("commit", {}).get("sha", "ok")


def push_repo_env(
    repo_dir: Path,
    env_file: Path | None = None,
    repo_name: str | None = None,
    org_name: str | None = None,
    gh_token: str | None = None,
    recipient: str | None = None,
    dest_name: str = "default.env",
    vault_repo: str = DEFAULT_VAULT_REPO,
) -> PushResult:
    """Encrypts local .env and commits to env-store vault."""
    resolved_env_file = env_file or (repo_dir / ".env")
    if not resolved_env_file.is_file():
        return PushResult(False, repo_name or "", "", message=f"Source .env file not found: {resolved_env_file}")

    detected_org, detected_name = detect_repo_name(repo_dir)
    final_repo = repo_name or detected_name
    final_org = org_name or detected_org or os.environ.get("GH_ORG_NAME") or os.environ.get("GH_ORG")
    final_token = resolve_gh_token(gh_token)
    final_recipient = recipient or DEFAULT_AGE_RECIPIENT

    if not final_org:
        return PushResult(False, final_repo, "", message="GitHub organization not found. Please set GH_ORG_NAME or pass -o <org>.")
    if not final_token:
        return PushResult(False, final_repo, "", message="GitHub token not found. Please set GH_TOKEN or GITHUB_TOKEN, log in via 'gh auth login', or pass -t/--token.")

    ensure_gitignore(repo_dir)

    with tempfile.NamedTemporaryFile("w+", suffix=".env", delete=False) as tmp_enc:
        tmp_enc_path = Path(tmp_enc.name)

    try:
        run_sops_encrypt(resolved_env_file, tmp_enc_path, final_recipient)
        ciphertext_bytes = tmp_enc_path.read_bytes()
        vault_path = f"{final_repo}/{dest_name}"
        sha = commit_to_env_store(
            owner=final_org,
            env_repo=vault_repo,
            path=vault_path,
            content_bytes=ciphertext_bytes,
            token=final_token,
        )
        return PushResult(True, final_repo, vault_path, commit_sha=sha, message="Pushed successfully.", org_name=final_org)
    finally:
        if tmp_enc_path.is_file():
            tmp_enc_path.unlink()


def push_repo_git_identity(
    repo_dir: Path,
    name: str | None = None,
    email: str | None = None,
    repo_name: str | None = None,
    org_name: str | None = None,
    gh_token: str | None = None,
    recipient: str | None = None,
    vault_repo: str = DEFAULT_VAULT_REPO,
) -> PushResult:
    """Encrypts repository-specific Git authorship and commits to <repo>/git.env in env-store."""
    detected_org, detected_name = detect_repo_name(repo_dir)
    final_repo = repo_name or detected_name
    final_org = org_name or detected_org or os.environ.get("GH_ORG_NAME") or os.environ.get("GH_ORG")
    final_token = resolve_gh_token(gh_token)
    final_recipient = recipient or DEFAULT_AGE_RECIPIENT

    if not final_org:
        return PushResult(False, final_repo, "", message="GitHub organization not found. Please set GH_ORG_NAME or pass -o <org>.")
    if not final_token:
        return PushResult(False, final_repo, "", message="GitHub token not found. Please set GH_TOKEN or GITHUB_TOKEN, log in via 'gh auth login', or pass -t/--token.")

    final_name = name or os.environ.get("GIT_AUTHOR_NAME")
    final_email = email or os.environ.get("GIT_AUTHOR_EMAIL")

    if not final_name or not final_email:
        try:
            if not final_name:
                res_n = subprocess.run(["git", "-C", str(repo_dir), "config", "user.name"], capture_output=True, text=True, check=False)
                if res_n.returncode == 0 and res_n.stdout.strip():
                    final_name = res_n.stdout.strip()
            if not final_email:
                res_e = subprocess.run(["git", "-C", str(repo_dir), "config", "user.email"], capture_output=True, text=True, check=False)
                if res_e.returncode == 0 and res_e.stdout.strip():
                    final_email = res_e.stdout.strip()
        except Exception:
            pass

    if not final_name or not final_email:
        return PushResult(
            False, final_repo, "",
            message="Git author name and email are required. Provide --name and --email, or configure git user.name and user.email.",
        )

    lines = [f"GIT_AUTHOR_NAME='{final_name}'", f"GIT_AUTHOR_EMAIL='{final_email}'"]
    raw_env_content = "\n".join(lines) + "\n"

    with tempfile.NamedTemporaryFile("w+", suffix=".env", delete=False) as tmp_src:
        tmp_src.write(raw_env_content)
        tmp_src_path = Path(tmp_src.name)

    with tempfile.NamedTemporaryFile("w+", suffix=".env", delete=False) as tmp_enc:
        tmp_enc_path = Path(tmp_enc.name)

    try:
        run_sops_encrypt(tmp_src_path, tmp_enc_path, final_recipient)
        ciphertext_bytes = tmp_enc_path.read_bytes()
        vault_path = f"{final_repo}/git.env"
        sha = commit_to_env_store(
            owner=final_org,
            env_repo=vault_repo,
            path=vault_path,
            content_bytes=ciphertext_bytes,
            token=final_token,
            commit_message=f"chore({final_repo}): update git.env authorship",
        )
        return PushResult(True, final_repo, vault_path, commit_sha=sha, message="Pushed git authorship successfully.", org_name=final_org)
    finally:
        if tmp_src_path.is_file():
            tmp_src_path.unlink()
        if tmp_enc_path.is_file():
            tmp_enc_path.unlink()


def main() -> None:
    # If first argument is 'git', dispatch to git sub-command parser
    is_git_subcommand = len(sys.argv) > 1 and sys.argv[1] == "git"

    if is_git_subcommand:
        git_parser = argparse.ArgumentParser(description="Push repository Git authorship (git.env) to env-store vault.")
        git_parser.add_argument("subcommand", choices=["git"])
        git_parser.add_argument("--name", help="Git author name (GIT_AUTHOR_NAME).")
        git_parser.add_argument("--email", help="Git author email (GIT_AUTHOR_EMAIL).")
        git_parser.add_argument("-r", "--repo", help="Target repository name (defaults to git remote origin).")
        git_parser.add_argument("-o", "--org", help="Target GitHub organization (defaults to GH_ORG_NAME).")
        git_parser.add_argument("-t", "--token", help="GitHub Personal Access Token.")
        git_parser.add_argument("--recipient", default=DEFAULT_AGE_RECIPIENT, help="Age public key recipient for encryption.")
        args = git_parser.parse_args()

        cwd = Path.cwd()
        res = push_repo_git_identity(
            repo_dir=cwd,
            name=args.name,
            email=args.email,
            repo_name=args.repo,
            org_name=args.org,
            gh_token=args.token,
            recipient=args.recipient,
        )
    else:
        parser = argparse.ArgumentParser(description="Push local project .env secrets to env-store vault.")
        parser.add_argument("-r", "--repo", help="Target repository name (defaults to git remote origin).")
        parser.add_argument("-o", "--org", help="Target GitHub organization (defaults to GH_ORG_NAME).")
        parser.add_argument("-t", "--token", help="GitHub Personal Access Token (defaults to GH_TOKEN / GITHUB_TOKEN / gh auth token).")
        parser.add_argument("-e", "--env", type=Path, default=Path(".env"), help="Path to local source .env file.")
        parser.add_argument("-d", "--dest", default="default.env", help="Destination file name in vault (default: default.env).")
        parser.add_argument("--recipient", default=DEFAULT_AGE_RECIPIENT, help="Age public key recipient for encryption.")
        args = parser.parse_args()

        cwd = Path.cwd()
        res = push_repo_env(
            repo_dir=cwd,
            env_file=args.env,
            repo_name=args.repo,
            org_name=args.org,
            gh_token=args.token,
            recipient=args.recipient,
            dest_name=args.dest,
        )

    if res.success:
        org_display = res.org_name or getattr(args, "org", None) or os.environ.get("GH_ORG_NAME") or "env-store"
        print(f"✅ Successfully encrypted and stored {res.target_path} in {org_display}/env-store.")
        print(f"   Commit SHA: {res.commit_sha}")
        print("🚀 Future modal-sandbox launches will automatically inject these settings!")
        sys.exit(0)
    else:
        print(f"❌ Failed to push: {res.message}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
