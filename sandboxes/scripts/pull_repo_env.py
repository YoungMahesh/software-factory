#!/usr/bin/env python3
"""Pull decrypted environment secrets from the Central Environment Store (env-store).

Retrieves and decrypts target repository secrets from github.com/${GH_ORG_NAME}/env-store
to a local workstation .env file as defined in ADR 0065.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

# Ensure repository root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from sandbox.env_store import (
    DEFAULT_VAULT_REPO,
    fetch_vault_env_bundle,
    fetch_vault_env_raw,
    fetch_vault_git_identity,
    is_sops_supported_format,
    resolve_gh_token,
)
from sandbox.env_store import detect_repo_name


def _resolve_repo_git_paths(
    dest_file: Path | None,
    final_dest: Path,
    cwd: Path,
) -> tuple[Path | None, Path | None]:
    """Resolves (repo_root, common_git_dir) only when dest belongs to a local Git checkout."""
    dest_root = final_dest.parent.resolve()
    candidates = [dest_root]
    if dest_file is None or dest_root == cwd.resolve():
        resolved_cwd = cwd.resolve()
        if resolved_cwd not in candidates:
            candidates.append(resolved_cwd)

    for candidate in candidates:
        git_marker = candidate / ".git"
        if not git_marker.exists():
            continue
        if git_marker.is_dir():
            return candidate, git_marker
        res = subprocess.run(
            ["git", "-C", str(candidate), "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            common_path = Path(res.stdout.strip())
            if not common_path.is_absolute():
                common_path = (candidate / common_path).resolve()
            return candidate, common_path
    return None, None


def _write_vault_cache(
    common_git_dir: Path | None,
    *,
    env_map_content: str,
    files: dict[str, str | bytes],
) -> None:
    """Stages decrypted vault files and env.map under <common_git_dir>/env-vault."""
    if common_git_dir is None or not common_git_dir.is_dir():
        return
    vault_dir = common_git_dir / "env-vault"
    vault_dir.mkdir(parents=True, exist_ok=True)
    try:
        vault_dir.chmod(0o700)
    except Exception:
        pass
    if env_map_content:
        mf = vault_dir / "env.map"
        mf.write_text(env_map_content, encoding="utf-8")
        mf.chmod(0o600)
    for sname, scontent in files.items():
        vf = vault_dir / sname
        vf.write_bytes(scontent.encode("utf-8") if isinstance(scontent, str) else scontent)
        vf.chmod(0o600)


def pull_repo_env(
    repo_name: str | None = None,
    org_name: str | None = None,
    dest_file: Path | None = None,
    gh_token: str | None = None,
    age_key: str | None = None,
    vault_repo: str = DEFAULT_VAULT_REPO,
    optional: bool = False,
) -> bool:
    """Pulls and decrypts environment secrets and Git identity from env-store."""
    cwd = Path.cwd()
    detected_org, detected_name = detect_repo_name(cwd)
    final_repo = repo_name or detected_name
    final_org = org_name or detected_org or os.environ.get("GH_ORG_NAME") or os.environ.get("GH_ORG")
    final_dest = dest_file or (cwd / ".env")

    token = resolve_gh_token(gh_token)
    if not token:
        if optional:
            print("ℹ️ GitHub token not found. Skipping optional env-store pull.", file=sys.stderr)
            return False
        print(
            "❌ GitHub token not found. Please set GH_TOKEN or GITHUB_TOKEN, log in via 'gh auth login', or pass --token.",
            file=sys.stderr,
        )
        return False

    if not final_org:
        if optional:
            print("ℹ️ GitHub organization not found. Skipping optional env-store pull.", file=sys.stderr)
            return False
        print(
            "❌ GitHub organization not found. Please set GH_ORG_NAME or pass -o <org>.",
            file=sys.stderr,
        )
        return False

    raw_env = None
    bundle = None
    try:
        bundle = fetch_vault_env_bundle(
            repo_name=final_repo,
            org_name=final_org,
            gh_token=token,
            age_key=age_key,
            env_repo_name=vault_repo,
        )
    except Exception as e:
        if optional:
            print(f"ℹ️ Could not decrypt secrets from env-store for repository '{final_repo}': {e}", file=sys.stderr)
            return False
        raise

    if bundle and bundle.get("files"):
        raw_env = bundle.get("files", {}).get("default.env") or (next(iter(bundle["files"].values())) if bundle.get("files") else None)

    git_configured = False
    repo_git_dir, common_git_dir = _resolve_repo_git_paths(dest_file, final_dest, cwd)
    if repo_git_dir:
        try:
            vault_git = fetch_vault_git_identity(
                repo_name=final_repo,
                org_name=final_org,
                gh_token=token,
                age_key=age_key,
                env_repo_name=vault_repo,
            )
            if vault_git:
                if vault_git.get("GIT_AUTHOR_NAME"):
                    subprocess.run(
                        ["git", "-C", str(repo_git_dir), "config", "--local", "user.name", vault_git["GIT_AUTHOR_NAME"]],
                        check=False,
                    )
                if vault_git.get("GIT_AUTHOR_EMAIL"):
                    subprocess.run(
                        ["git", "-C", str(repo_git_dir), "config", "--local", "user.email", vault_git["GIT_AUTHOR_EMAIL"]],
                        check=False,
                    )
                git_configured = True
                print(
                    f"👤 Configured repository git author for {final_repo}: "
                    f"{vault_git.get('GIT_AUTHOR_NAME', '')} <{vault_git.get('GIT_AUTHOR_EMAIL', '')}>"
                )
        except Exception:
            pass

    if raw_env is None and not git_configured:
        if optional:
            print(f"ℹ️ No secrets found for repository '{final_repo}' in env-store ({vault_repo}).", file=sys.stderr)
        return False

    if bundle and bundle.get("mappings") and bundle.get("files"):
        _write_vault_cache(
            common_git_dir,
            env_map_content=bundle.get("env_map_content") or "",
            files=bundle["files"],
        )

        base_dir = repo_git_dir or final_dest.parent
        for sname, drel in bundle["mappings"]:
            if sname in bundle["files"]:
                target_f = (base_dir / drel) if drel != ".env" else final_dest
                target_f.parent.mkdir(parents=True, exist_ok=True)
                content = bundle["files"][sname]
                if is_sops_supported_format(sname):
                    if isinstance(content, str) and not content.endswith("\n"):
                        content += "\n"
                target_f.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
                target_f.chmod(0o600)
    elif raw_env is not None:
        final_dest.parent.mkdir(parents=True, exist_ok=True)
        if raw_env and not raw_env.endswith("\n"):
            raw_env += "\n"
        final_dest.write_text(raw_env, encoding="utf-8")
        final_dest.chmod(0o600)
        _write_vault_cache(
            common_git_dir,
            env_map_content="default.env=.env\n",
            files={"default.env": raw_env},
        )

    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Pull decrypted .env secrets from env-store vault.")
    parser.add_argument("-r", "--repo", help="Target repository name (defaults to git remote origin).")
    parser.add_argument("-o", "--org", help="Target GitHub organization (defaults to GH_ORG_NAME).")
    parser.add_argument("-t", "--token", help="GitHub Personal Access Token (defaults to GH_TOKEN / GITHUB_TOKEN / gh auth token).")
    parser.add_argument("-k", "--key", help="Age private key (defaults to AGE_PRIVATE_KEY / SOPS_AGE_KEY).")
    parser.add_argument("-d", "--dest", type=Path, default=Path(".env"), help="Path to destination .env file.")
    parser.add_argument(
        "--optional",
        "--ignore-missing",
        dest="optional",
        action="store_true",
        help="Do not exit with error if secrets are missing or decryption keys are unavailable.",
    )
    args = parser.parse_args()

    cwd = Path.cwd()
    _, detected_name = detect_repo_name(cwd)
    target_repo = args.repo or detected_name

    success = pull_repo_env(
        repo_name=args.repo,
        org_name=args.org,
        dest_file=args.dest,
        gh_token=args.token,
        age_key=args.key,
        optional=args.optional,
    )
    if success:
        if args.dest.is_file():
            print(f"✅ Successfully pulled and decrypted secrets into {args.dest.resolve()} (mode 0600).")
        else:
            print(f"✅ Successfully pulled repository settings for {target_repo}.")
        sys.exit(0)
    elif args.optional:
        sys.exit(0)
    else:
        print(
            f"❌ Could not find or decrypt secrets for repository '{target_repo}' in env-store.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
