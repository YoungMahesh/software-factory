"""Central Environment Store vault resolver module.

Retrieves and decrypts target repository secrets from the private
github.com/${GH_ORG_NAME}/env-store vault host-side for injection
into Modal sandboxes as defined in ADR 0057 and ADR 0067.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
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
SOPS_SUPPORTED_EXTENSIONS = {".env", ".json", ".yaml", ".yml", ".ini"}

def get_file_extension(filename: str | Path) -> str:
    """Returns lowercased suffix or .env if file is named .env."""
    name = Path(filename).name
    return ".env" if name == ".env" else Path(filename).suffix.lower()

def is_sops_supported_format(filename: str | Path) -> bool:
    """Checks whether the filename extension is recognized by SOPS."""
    return get_file_extension(filename) in SOPS_SUPPORTED_EXTENSIONS

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
        if line and not line.startswith("#") and "=" in line:
            src, dest = line.split("=", 1)
            s, d = src.strip(), dest.strip().lstrip("/")
            if s and d:
                mappings.append((s, d))
    return mappings

def update_env_map_content(raw_text: str | None, src_name: str, dest_rel_path: str) -> str:
    """Updates or appends a mapping in env.map content, ensuring uniqueness by src_name."""
    lines, found, clean_dest = [], False, dest_rel_path.strip().lstrip("/")
    if raw_text:
        for line in raw_text.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in line:
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
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json", "User-Agent": "software-factory-env-store"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return base64.b64decode(data["content"]).decode("utf-8") if isinstance(data, dict) and "content" in data else None
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    except Exception:
        return None

def decrypt_sops_payload(ciphertext: str, age_private_key: str | None = None, target_filename: str | None = None) -> str:
    """Decrypts a SOPS-encrypted payload string returning plaintext."""
    if not shutil.which("sops"):
        raise RuntimeError("sops executable not found in PATH.")

    env = os.environ.copy()
    if age_private_key:
        env["SOPS_AGE_KEY"] = age_private_key.strip()
    elif "SOPS_AGE_KEY" not in env and DEFAULT_KEY_FILE.is_file():
        env["SOPS_AGE_KEY_FILE"] = str(DEFAULT_KEY_FILE)

    suffix = Path(target_filename).suffix if target_filename else ".env"
    with tempfile.NamedTemporaryFile("w+", suffix=suffix or ".env", delete=False) as tmp:
        tmp.write(ciphertext)
        tmp_path = Path(tmp.name)

    try:
        cmd = ["sops", "decrypt"]
        if target_filename:
            cmd.extend(["--filename-override", target_filename])
        cmd.append(str(tmp_path))
        res = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)
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

    try:
        return decrypt_sops_payload(ciphertext, age_private_key=resolved_age_key, target_filename=target_filename)
    except TypeError:
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
    raw_text = fetch_vault_env_raw(repo_name=repo_name, org_name=org_name, gh_token=gh_token, age_key=age_key, env_repo_name=env_repo_name, target_filename=target_filename)
    return parse_env_text(raw_text) if raw_text is not None else None

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
    mappings = parse_env_map(raw_env_map) if raw_env_map else []
    files: dict[str, str] = {}

    if mappings:
        for src, dest in mappings:
            try:
                decrypted = fetch_vault_env_raw(repo_name=bare_repo, org_name=resolved_org, gh_token=resolved_token, age_key=resolved_age_key, env_repo_name=env_repo_name, target_filename=src)
                if decrypted is not None:
                    files[src] = decrypted
                else:
                    warnings.warn(f"Mapped secret file '{src}' not found in {bare_repo} env-store.", UserWarning, stacklevel=2)
            except Exception as e:
                warnings.warn(f"Failed to decrypt mapped secret file '{src}' for {bare_repo}: {e}", UserWarning, stacklevel=2)
        return {"env_map_content": raw_env_map, "mappings": mappings, "files": files}

    default_env_text = fetch_vault_env_raw(repo_name=bare_repo, org_name=resolved_org, gh_token=resolved_token, age_key=resolved_age_key, env_repo_name=env_repo_name, target_filename="default.env")
    if default_env_text is not None:
        return {"env_map_content": "default.env=.env\n", "mappings": [("default.env", ".env")], "files": {"default.env": default_env_text}}
    return None

def fetch_vault_git_identity(
    repo_name: str,
    org_name: str | None = None,
    gh_token: str | None = None,
    age_key: str | None = None,
    env_repo_name: str = DEFAULT_VAULT_REPO,
) -> dict[str, str] | None:
    """Fetches and decrypts repository-specific git authorship from <repo>/git.env in env-store."""
    return fetch_vault_env(repo_name=repo_name, org_name=org_name, gh_token=gh_token, age_key=age_key, env_repo_name=env_repo_name, target_filename="git.env")


@dataclass
class VaultBundle:
    """Encapsulated domain bundle containing decrypted secrets, base64 payload, and Git identity."""
    env_dict: dict[str, str] = field(default_factory=dict)
    encoded_bundle: str | None = None
    dotenv_b64: str | None = None
    git_author_name: str | None = None
    git_author_email: str | None = None
    tz: str | None = None
    files: dict[str, str] = field(default_factory=dict)


def resolve_sandbox_bundle(
    repo_name: str,
    org_name: str | None = None,
    gh_token: str | None = None,
    age_key: str | None = None,
    env_repo_name: str = DEFAULT_VAULT_REPO,
) -> VaultBundle | None:
    """Resolves and packages sandbox secrets, base64 payloads, and Git identity into a single domain bundle."""
    bundle = fetch_vault_env_bundle(
        repo_name=repo_name,
        org_name=org_name,
        gh_token=gh_token,
        age_key=age_key,
        env_repo_name=env_repo_name,
    )
    all_vars: dict[str, str] = {}
    raw_vault_env = None
    encoded_bundle = None

    if bundle and bundle.get("files"):
        encoded_bundle = base64.b64encode(json.dumps(bundle).encode("utf-8")).decode("ascii")
        for content in bundle["files"].values():
            if isinstance(content, str):
                all_vars.update(parse_env_text(content))
        raw_vault_env = bundle["files"].get("default.env") or next(iter(bundle["files"].values()), None)
    else:
        raw_vault_env = fetch_vault_env_raw(
            repo_name=repo_name,
            org_name=org_name,
            gh_token=gh_token,
            age_key=age_key,
            env_repo_name=env_repo_name,
        )
        if raw_vault_env is not None:
            all_vars = parse_env_text(raw_vault_env)
        else:
            fetched = fetch_vault_env(
                repo_name=repo_name,
                org_name=org_name,
                gh_token=gh_token,
                age_key=age_key,
                env_repo_name=env_repo_name,
            )
            if fetched is not None:
                all_vars = fetched
                raw_vault_env = serialize_env_dict(fetched)

    if not all_vars and not raw_vault_env and not bundle:
        return None

    dotenv_b64 = base64.b64encode(raw_vault_env.encode("utf-8")).decode("ascii") if raw_vault_env else None
    git_ident = fetch_vault_git_identity(
        repo_name=repo_name,
        org_name=org_name,
        gh_token=gh_token,
        age_key=age_key,
        env_repo_name=env_repo_name,
    ) or {}

    return VaultBundle(
        env_dict=all_vars,
        encoded_bundle=encoded_bundle,
        dotenv_b64=dotenv_b64,
        git_author_name=git_ident.get("GIT_AUTHOR_NAME"),
        git_author_email=git_ident.get("GIT_AUTHOR_EMAIL"),
        tz=all_vars.get("TZ"),
        files=bundle.get("files", {}) if bundle else {},
    )


class EnvStoreVault:
    """Domain adapter encapsulating Central Environment Store pull, push, and bundle operations."""

    def __init__(
        self,
        org_name: str | None = None,
        gh_token: str | None = None,
        age_key: str | None = None,
        vault_repo: str = DEFAULT_VAULT_REPO,
    ):
        self.org_name = org_name or os.environ.get("GH_ORG_NAME") or os.environ.get("GH_ORG")
        self.gh_token = resolve_gh_token(gh_token)
        self.age_key = age_key or os.environ.get("AGE_PRIVATE_KEY") or os.environ.get("SOPS_AGE_KEY")
        self.vault_repo = vault_repo

    def resolve_sandbox_bundle(self, repo_name: str) -> VaultBundle | None:
        """Resolves target repository sandbox secrets as an encapsulated VaultBundle."""
        return resolve_sandbox_bundle(
            repo_name=repo_name,
            org_name=self.org_name,
            gh_token=self.gh_token,
            age_key=self.age_key,
            env_repo_name=self.vault_repo,
        )

    def pull(
        self,
        repo_name: str | None = None,
        dest_file: Path | None = None,
        optional: bool = False,
    ) -> bool:
        """Pulls target repository environment secrets to a local .env destination."""
        from scripts.pull_repo_env import pull_repo_env
        return pull_repo_env(
            repo_name=repo_name,
            org_name=self.org_name,
            dest_file=dest_file,
            gh_token=self.gh_token,
            age_key=self.age_key,
            vault_repo=self.vault_repo,
            optional=optional,
        )

    def push(
        self,
        repo_dir: Path,
        env_file: Path | None = None,
        repo_name: str | None = None,
        dest_name: str | None = None,
        allow_binary: bool = False,
    ) -> PushResult:
        """Encrypts and pushes local environment secrets to env-store."""
        return push_repo_env(
            repo_dir=repo_dir,
            env_file=env_file,
            repo_name=repo_name,
            org_name=self.org_name,
            gh_token=self.gh_token,
            dest_name=dest_name,
            vault_repo=self.vault_repo,
            allow_binary=allow_binary,
        )


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


from sandbox.env_store_push import (
    DEFAULT_AGE_RECIPIENT,
    PushResult,
    commit_to_env_store,
    ensure_gitignore,
    push_repo_env,
    push_repo_git_identity,
    run_sops_encrypt,
)
