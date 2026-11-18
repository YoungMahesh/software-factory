"""Central Environment Store vault resolver module.

Retrieves and decrypts target repository secrets from the private
github.com/${GH_ORG_NAME}/env-store vault host-side for injection
into Modal sandboxes as defined in ADR 0057 and ADR 0067.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any
import urllib.error
import urllib.request
import warnings

DEFAULT_KEY_FILE = Path.home() / ".config" / "sops" / "age" / "keys.txt"
DEFAULT_VAULT_REPO = "env-store"

def parse_env_text(raw_text: str) -> dict[str, str]:
    """Parses .env string content into a dictionary of key-value pairs."""
    from sandbox.config import parse_env_file
    return parse_env_file(raw_text)

def serialize_env_dict(env_dict: dict[str, str]) -> str:
    """Serializes a dictionary of environment variables into a .env string."""
    lines: list[str] = []
    for k, v in env_dict.items():
        if any(c in v for c in (" ", "\t", "\n", "#", "'", '"')):
            val = f"'{v}'" if "'" not in v else (f'"{v}"' if '"' not in v else f"'{v.replace('\'', '\'\\\'\'')}'")
            lines.append(f"{k}={val}")
        else:
            lines.append(f"{k}={v}")
    return "\n".join(lines) + ("\n" if lines else "")

def is_encrypted_sops_payload(raw_text: str) -> bool:
    """Checks if text appears to be a SOPS-encrypted file or JSON/YAML manifest."""
    indicators = ("sops:", "ENC[AES", "ENC[", '"sops":', "mac: ENC")
    return any(ind in raw_text for ind in indicators)

def parse_env_map(raw_text: str) -> list[tuple[str, str]]:
    """Parses plaintext env.map content returning a list of (src_rel, dest_rel) tuples."""
    if is_encrypted_sops_payload(raw_text):
        warnings.warn("env.map is encrypted with SOPS. env.map must be a plaintext manifest. Skipping decryption.", UserWarning, stacklevel=2)
        return []

    mappings: list[tuple[str, str]] = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            src, dest = line.split("=", 1)
            src = src.strip()
            dest = dest.strip().lstrip("/")
            if src and dest:
                mappings.append((src, dest))
    return mappings

def update_env_map_content(raw_text: str | None, src_name: str, dest_rel_path: str) -> str:
    """Updates or appends a mapping in env.map content, ensuring uniqueness by src_name."""
    lines: list[str] = []
    found = False
    clean_dest = dest_rel_path.strip().lstrip("/")
    if raw_text:
        for line in raw_text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                lines.append(line)
                continue
            if "=" in line:
                s, _ = line.split("=", 1)
                if s.strip() == src_name:
                    lines.append(f"{src_name} = {clean_dest}")
                    found = True
                    continue
            lines.append(line)
    if not found:
        lines.append(f"{src_name} = {clean_dest}")
    return "\n".join(lines).strip() + "\n"

def resolve_gh_token(explicit_token: str | None = None) -> str | None:
    """Resolves GitHub token from explicit arg, env (GH_TOKEN/GITHUB_TOKEN), or gh CLI."""
    if explicit_token and explicit_token.strip():
        return explicit_token.strip()
    from_env = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if from_env and from_env.strip():
        return from_env.strip()
    if shutil.which("gh"):
        try:
            res = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=False)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception:
            pass
    return None

def fetch_github_file(owner: str, repo: str, path: str, token: str) -> str | None:
    """Fetches a file from GitHub repository using the Contents REST API."""
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "software-factory-env-store",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict) and "content" in data:
                return base64.b64decode(data["content"]).decode("utf-8")
            return None
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    except Exception:
        return None

def decrypt_sops_payload(ciphertext: str, age_private_key: str | None = None) -> str:
    """Decrypts a SOPS-encrypted payload string returning plaintext."""
    if not shutil.which("sops"):
        raise RuntimeError("sops executable not found in PATH.")

    env = os.environ.copy()
    if age_private_key:
        env["SOPS_AGE_KEY"] = age_private_key.strip()
    elif "SOPS_AGE_KEY" not in env and DEFAULT_KEY_FILE.is_file():
        env["SOPS_AGE_KEY_FILE"] = str(DEFAULT_KEY_FILE)

    with tempfile.NamedTemporaryFile("w+", suffix=".env", delete=False) as tmp:
        tmp.write(ciphertext)
        tmp_path = Path(tmp.name)

    try:
        res = subprocess.run(["sops", "decrypt", str(tmp_path)], capture_output=True, text=True, env=env, check=False)
        if res.returncode != 0:
            raise RuntimeError(f"SOPS decryption failed: {res.stderr.strip()}")
        return res.stdout
    finally:
        if tmp_path.is_file():
            tmp_path.unlink()

def fetch_vault_env_raw(
    repo_name: str,
    org_name: str | None = None,
    gh_token: str | None = None,
    age_key: str | None = None,
    env_repo_name: str = DEFAULT_VAULT_REPO,
    target_filename: str = "default.env",
) -> str | None:
    """Fetches and decrypts environment file text for a target repository from env-store."""
    clean_repo = repo_name.strip().rstrip("/")
    bare_repo = clean_repo.split("/", 1)[1] if "/" in clean_repo else clean_repo
    resolved_org = org_name or os.environ.get("GH_ORG_NAME") or os.environ.get("GH_ORG")
    resolved_token = resolve_gh_token(gh_token)
    resolved_age_key = age_key or os.environ.get("AGE_PRIVATE_KEY") or os.environ.get("SOPS_AGE_KEY")

    if not resolved_org or not resolved_token:
        return None

    file_path = f"{bare_repo}/{target_filename}"
    ciphertext = fetch_github_file(resolved_org, env_repo_name, file_path, token=resolved_token)
    if not ciphertext:
        return None

    return decrypt_sops_payload(ciphertext, age_private_key=resolved_age_key)

def fetch_vault_env(
    repo_name: str,
    org_name: str | None = None,
    gh_token: str | None = None,
    age_key: str | None = None,
    env_repo_name: str = DEFAULT_VAULT_REPO,
    target_filename: str = "default.env",
) -> dict[str, str] | None:
    """Fetches and decrypts environment variables for a target repository from env-store."""
    raw_text = fetch_vault_env_raw(
        repo_name=repo_name,
        org_name=org_name,
        gh_token=gh_token,
        age_key=age_key,
        env_repo_name=env_repo_name,
        target_filename=target_filename,
    )
    if raw_text is None:
        return None
    return parse_env_text(raw_text)

def fetch_vault_env_bundle(
    repo_name: str,
    org_name: str | None = None,
    gh_token: str | None = None,
    age_key: str | None = None,
    env_repo_name: str = DEFAULT_VAULT_REPO,
) -> dict[str, Any] | None:
    """Fetches environment bundle (mapped files + manifest) for a repository from env-store."""
    clean_repo = repo_name.strip().rstrip("/")
    bare_repo = clean_repo.split("/", 1)[1] if "/" in clean_repo else clean_repo
    resolved_org = org_name or os.environ.get("GH_ORG_NAME") or os.environ.get("GH_ORG")
    resolved_token = resolve_gh_token(gh_token)
    resolved_age_key = age_key or os.environ.get("AGE_PRIVATE_KEY") or os.environ.get("SOPS_AGE_KEY")

    if not resolved_org or not resolved_token:
        return None

    env_map_path = f"{bare_repo}/env.map"
    raw_env_map = fetch_github_file(resolved_org, env_repo_name, env_map_path, token=resolved_token)

    mappings: list[tuple[str, str]] = []
    if raw_env_map:
        mappings = parse_env_map(raw_env_map)

    files: dict[str, str] = {}

    if mappings:
        for src, dest in mappings:
            try:
                decrypted = fetch_vault_env_raw(
                    repo_name=bare_repo,
                    org_name=resolved_org,
                    gh_token=resolved_token,
                    age_key=resolved_age_key,
                    env_repo_name=env_repo_name,
                    target_filename=src,
                )
                if decrypted is not None:
                    files[src] = decrypted
                else:
                    warnings.warn(f"Mapped secret file '{src}' not found in {bare_repo} env-store.", UserWarning, stacklevel=2)
            except Exception as e:
                warnings.warn(f"Failed to decrypt mapped secret file '{src}' for {bare_repo}: {e}", UserWarning, stacklevel=2)

        return {"env_map_content": raw_env_map, "mappings": mappings, "files": files}

    default_env_text = fetch_vault_env_raw(
        repo_name=bare_repo,
        org_name=resolved_org,
        gh_token=resolved_token,
        age_key=resolved_age_key,
        env_repo_name=env_repo_name,
        target_filename="default.env",
    )
    if default_env_text is not None:
        return {
            "env_map_content": "default.env=.env\n",
            "mappings": [("default.env", ".env")],
            "files": {"default.env": default_env_text},
        }

    return None

def fetch_vault_git_identity(
    repo_name: str,
    org_name: str | None = None,
    gh_token: str | None = None,
    age_key: str | None = None,
    env_repo_name: str = DEFAULT_VAULT_REPO,
) -> dict[str, str] | None:
    """Fetches and decrypts repository-specific git authorship from <repo>/git.env in env-store."""
    return fetch_vault_env(
        repo_name=repo_name,
        org_name=org_name,
        gh_token=gh_token,
        age_key=age_key,
        env_repo_name=env_repo_name,
        target_filename="git.env",
    )

DEFAULT_AGE_RECIPIENT = "age1zwr6flwyk3lt6k0xsd9wy0qy4dlytkdyv5aggvqu6zxqt3p2eyrsw5n4qj"

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
    if not gitignore.is_file():
        gitignore.write_text(".env*\n", encoding="utf-8")
        return True
    content = gitignore.read_text(encoding="utf-8")
    if any(p in (".env", ".env*", ".env.*") for p in [l.strip() for l in content.splitlines()]):
        return False
    with open(gitignore, "a", encoding="utf-8") as f:
        f.write(("" if content.endswith("\n") or not content else "\n") + ".env*\n")
    return True

def detect_repo_name(repo_dir: Path | str | None = None) -> tuple[str | None, str]:
    """Detects GitHub owner and repository name from git remote origin."""
    path = Path(repo_dir) if repo_dir else Path.cwd()
    try:
        res = subprocess.run(["git", "-C", str(path), "remote", "get-url", "origin"], capture_output=True, text=True, check=False)
        if res.returncode == 0 and res.stdout.strip():
            m = re.search(r"github\.com[:/]([^/]+)/([^/\.]+)(?:\.git)?$", res.stdout.strip())
            if m:
                return m.group(1), m.group(2)
    except Exception:
        pass
    return None, path.resolve().name

def run_sops_encrypt(src_file: Path, dest_file: Path, recipient: str) -> None:
    """Encrypts src_file with SOPS using recipient Age key."""
    if not shutil.which("sops"):
        raise RuntimeError("sops executable not found in PATH.")
    res = subprocess.run(["sops", "--encrypt", "--age", recipient, str(src_file)], capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"SOPS encryption failed: {res.stderr.strip()}")
    dest_file.write_text(res.stdout, encoding="utf-8")

def commit_to_env_store(
    owner: str, env_repo: str, path: str, content_bytes: bytes, token: str, commit_message: str | None = None,
) -> str:
    """Commits or updates a file in env-store using GitHub Contents REST API."""
    url = f"https://api.github.com/repos/{owner}/{env_repo}/contents/{path}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json", "User-Agent": "push-repo-env"}
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
    body: dict[str, str] = {"message": msg, "content": base64.b64encode(content_bytes).decode("ascii")}
    if sha:
        body["sha"] = sha
    req_put = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={**headers, "Content-Type": "application/json"}, method="PUT")
    with urllib.request.urlopen(req_put) as put_resp:
        return json.loads(put_resp.read().decode("utf-8")).get("commit", {}).get("sha", "ok")

def _encrypt_and_commit(
    src_path: Path, owner: str, vault_repo: str, vault_path: str,
    token: str, recipient: str, commit_msg: str | None = None,
    encrypt_fn: Any = None, commit_fn: Any = None,
) -> str:
    enc = encrypt_fn or run_sops_encrypt
    com = commit_fn or commit_to_env_store
    with tempfile.NamedTemporaryFile("w+", suffix=".env", delete=False) as tmp_enc:
        tmp_enc_path = Path(tmp_enc.name)
    try:
        enc(src_path, tmp_enc_path, recipient)
        return com(owner=owner, env_repo=vault_repo, path=vault_path, content_bytes=tmp_enc_path.read_bytes(), token=token, commit_message=commit_msg)
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
            return PushResult(False, repo_name or "", "", message=f"When source environment file is not '.env' ('{src.name}'), you must also pass -d/--dest to define the destination in env-store.")

    det_org, det_name = detect_repo_name(repo_dir)
    final_repo = repo_name or det_name
    final_org = org_name or det_org or os.environ.get("GH_ORG_NAME") or os.environ.get("GH_ORG")
    token = resolve_gh_token(gh_token)
    recip = recipient or DEFAULT_AGE_RECIPIENT

    if not final_org:
        return PushResult(False, final_repo, "", message="GitHub organization not found. Please set GH_ORG_NAME or pass -o <org>.")
    if not token:
        return PushResult(False, final_repo, "", message="GitHub token not found. Please set GH_TOKEN or GITHUB_TOKEN, log in via 'gh auth login', or pass -t/--token.")

    ensure_gitignore(repo_dir)
    vault_path = f"{final_repo}/{dest_name}"
    sha = _encrypt_and_commit(src, final_org, vault_repo, vault_path, token, recip, encrypt_fn=encrypt_fn, commit_fn=commit_fn)

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
                    locals()[attr] = res.stdout.strip()
                    if attr == "final_name": final_name = res.stdout.strip()
                    if attr == "final_email": final_email = res.stdout.strip()

    if not final_name or not final_email:
        return PushResult(False, final_repo, "", message="Git author name and email are required. Provide --name and --email, or configure git user.name and user.email.")

    raw_env_content = f"GIT_AUTHOR_NAME='{final_name}'\nGIT_AUTHOR_EMAIL='{final_email}'\n"
    with tempfile.NamedTemporaryFile("w+", suffix=".env", delete=False) as tmp_src:
        tmp_src.write(raw_env_content)
        tmp_src_path = Path(tmp_src.name)
    try:
        vault_path = f"{final_repo}/git.env"
        sha = _encrypt_and_commit(tmp_src_path, final_org, vault_repo, vault_path, token, recip, commit_msg=f"chore({final_repo}): update git.env authorship", encrypt_fn=encrypt_fn, commit_fn=commit_fn)
        return PushResult(True, final_repo, vault_path, commit_sha=sha, message="Pushed git authorship successfully.", org_name=final_org)
    finally:
        if tmp_src_path.is_file():
            tmp_src_path.unlink()
