"""Manifest-driven and single-file env-store push orchestration."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

from sandbox.env_store_push._transport import (
    NonInteractivePromptError,
    PushFileOutcome,
    PushResult,
    _encrypt_and_commit,
    _resolve_repo_context,
    commit_to_env_store,
    ensure_gitignore,
)


def _normalize_map_dest(repo_root: Path, dest_rel: str) -> str | None:
    """Resolves an env.map destination path inside repo_root, or None if invalid/escaping."""
    clean = dest_rel.strip().lstrip("/")
    if not clean:
        return None
    try:
        return (repo_root / clean).resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return None


def _resolve_repo_rel_path(repo_root: Path, src: Path) -> tuple[str, bool]:
    """Returns normalized POSIX relative path and whether src resides inside repo_root."""
    try:
        return src.resolve().relative_to(repo_root).as_posix(), True
    except ValueError:
        return src.name, False


def _prompt_user_for_file(rel_path: str, vault_path: str) -> bool:
    """Interactively prompts the user [y/N] to confirm pushing a file."""
    if not sys.stdin.isatty():
        raise NonInteractivePromptError(
            "Multiple or non-root environment files found in env.map, but stdin is not interactive. "
            "Pass --all to push all mapped files or -e <path> to push a single file."
        )
    while True:
        try:
            answer = input(f"Push '{rel_path}' -> '{vault_path}' to env-store? [y/N]: ").strip().lower()
        except EOFError:
            return False
        if answer in ("y", "yes"):
            return True
        if answer in ("", "n", "no"):
            return False
        print("Please answer 'y' (yes) or 'n' (no).", file=sys.stderr)


def _fetch_and_parse_env_map(
    fetch_f: Any,
    owner: str,
    vault_repo: str,
    repo_name: str,
    token: str,
) -> tuple[str | None, list[tuple[str, str]]]:
    """Fetches env.map from env-store and parses plaintext entries, failing on encrypted manifests."""
    from sandbox.env_store import is_encrypted_sops_payload, parse_env_map

    map_path = f"{repo_name}/env.map"
    raw_map = fetch_f(owner, vault_repo, map_path, token=token)
    if raw_map is not None and is_encrypted_sops_payload(raw_map):
        raise ValueError(
            f"Remote {map_path} in {owner}/{vault_repo} appears to be SOPS-encrypted. "
            "env.map must be a plaintext manifest; refusing to overwrite it."
        )
    mappings = parse_env_map(raw_map) if raw_map else []
    return raw_map, mappings


def _commit_env_map_if_changed(
    com_f: Any,
    owner: str,
    vault_repo: str,
    repo_name: str,
    token: str,
    raw_map: str | None,
    new_map: str,
) -> None:
    """Commits updated env.map manifest when content differs from remote."""
    if new_map != (raw_map or ""):
        com_f(
            owner=owner,
            env_repo=vault_repo,
            path=f"{repo_name}/env.map",
            content_bytes=new_map.encode("utf-8"),
            token=token,
            commit_message=f"chore({repo_name}): update env.map manifest",
        )


def _unsupported_ext_message(dest_name: str) -> str:
    from sandbox.env_store import SOPS_SUPPORTED_EXTENSIONS, get_file_extension

    ext = get_file_extension(dest_name) or "(no extension)"
    valid = ", ".join(sorted(SOPS_SUPPORTED_EXTENSIONS))
    return (
        f"Destination file '{dest_name}' has unsupported extension '{ext}'. "
        f"Supported formats: {valid}. Pass --allow-binary to allow encrypting arbitrary or binary files."
    )


def _push_single_file(
    repo_dir: Path,
    env_file: Path | None,
    dest_name: str | None,
    final_repo: str,
    final_org: str,
    token: str,
    recip: str,
    vault_repo: str,
    allow_binary: bool,
    encrypt_fn: Any,
    commit_fn: Any,
    fetch_f: Any,
    com_f: Any,
) -> PushResult:
    """Pushes a single explicit source file, resolving existing mappings in env.map when dest_name is omitted."""
    from sandbox.env_store import is_sops_supported_format, update_env_map_content

    src = (repo_dir / ".env") if env_file is None else (env_file if env_file.is_absolute() else (repo_dir / env_file))
    if not src.is_file():
        return PushResult(False, final_repo, "", message=f"Source .env file not found: {src}")

    if dest_name is not None and not is_sops_supported_format(dest_name) and not allow_binary:
        return PushResult(False, final_repo, "", message=_unsupported_ext_message(dest_name))

    try:
        raw_map, mappings = _fetch_and_parse_env_map(fetch_f, final_org, vault_repo, final_repo, token)
    except ValueError as exc:
        return PushResult(False, final_repo, "", message=str(exc), org_name=final_org)

    repo_root = repo_dir.resolve()
    rel_dest, in_repo = _resolve_repo_rel_path(repo_root, src)
    matched_from_map = False

    if not dest_name:
        matches = (
            list(dict.fromkeys(s for s, d in mappings if _normalize_map_dest(repo_root, d) == rel_dest))
            if in_repo
            else []
        )
        if len(matches) == 1:
            dest_name = matches[0]
            matched_from_map = True
        elif len(matches) > 1:
            return PushResult(
                False,
                final_repo,
                "",
                message=(
                    f"Multiple entries in env.map map to '{rel_dest}' ({', '.join(matches)}). "
                    "Pass -d/--dest to specify which vault destination to update."
                ),
                org_name=final_org,
            )
        elif in_repo and rel_dest == ".env":
            dest_name = "default.env"
        else:
            return PushResult(
                False,
                final_repo,
                "",
                message=(
                    f"Source environment file '{rel_dest}' is not mapped in env.map and is not root '.env'. "
                    "You must pass -d/--dest to define its destination in env-store."
                ),
                org_name=final_org,
            )

    if not is_sops_supported_format(dest_name) and not allow_binary and not matched_from_map:
        return PushResult(False, final_repo, "", message=_unsupported_ext_message(dest_name))

    ensure_gitignore(repo_dir)
    vault_path = f"{final_repo}/{dest_name}"
    sha = _encrypt_and_commit(
        src, final_org, vault_repo, vault_path, token, recip,
        encrypt_fn=encrypt_fn, commit_fn=commit_fn, filename_override=dest_name,
    )

    new_map = update_env_map_content(raw_map, dest_name, rel_dest)
    if raw_map is None and dest_name != "default.env":
        if fetch_f(final_org, vault_repo, f"{final_repo}/default.env", token=token):
            new_map = update_env_map_content(new_map, "default.env", ".env")
    _commit_env_map_if_changed(com_f, final_org, vault_repo, final_repo, token, raw_map, new_map)

    outcome = PushFileOutcome(dest_name, rel_dest, vault_path, True, commit_sha=sha, message="Pushed successfully.")
    return PushResult(
        True, final_repo, vault_path, commit_sha=sha,
        message="Pushed successfully.", org_name=final_org, pushed_files=[outcome],
    )


def _push_from_env_map(
    repo_dir: Path,
    final_repo: str,
    final_org: str,
    token: str,
    recip: str,
    vault_repo: str,
    push_all: bool,
    encrypt_fn: Any,
    commit_fn: Any,
    fetch_f: Any,
    com_f: Any,
    prompt_fn: Any,
) -> PushResult:
    """Checks env.map in env-store and pushes mapped local files (plus unmapped root .env)."""
    from sandbox.env_store import update_env_map_content

    try:
        raw_map, mappings = _fetch_and_parse_env_map(fetch_f, final_org, vault_repo, final_repo, token)
    except ValueError as exc:
        return PushResult(False, final_repo, "", message=str(exc), org_name=final_org)

    repo_root = repo_dir.resolve()
    candidates: list[tuple[str, str]] = []
    unmapped_root_dotenv = False

    if mappings:
        for src_name, dest_rel in mappings:
            norm = _normalize_map_dest(repo_root, dest_rel)
            if norm is None:
                return PushResult(
                    False, final_repo, "",
                    message=f"Invalid path in env.map escapes repository root: '{dest_rel}'",
                    org_name=final_org,
                )
            candidates.append((src_name, norm))
        if (repo_root / ".env").is_file() and all(d != ".env" for _, d in candidates) and all(s != "default.env" for s, _ in candidates):
            candidates.append(("default.env", ".env"))
            unmapped_root_dotenv = True
    else:
        if not (repo_root / ".env").is_file():
            return PushResult(False, final_repo, "", message=f"Source .env file not found: {repo_dir / '.env'}", org_name=final_org)
        candidates = [("default.env", ".env")]
        unmapped_root_dotenv = True

    existing: list[tuple[str, str]] = []
    skipped: list[str] = []
    for vault_name, rel_path in candidates:
        if (repo_root / rel_path).is_file():
            existing.append((vault_name, rel_path))
        else:
            skipped.append(rel_path)
            print(f"⚠️  Skipping missing local file '{rel_path}' (mapped to '{vault_name}').", file=sys.stderr)

    if not existing:
        return PushResult(
            False, final_repo, "",
            message="None of the files mapped in env.map exist locally.",
            org_name=final_org, skipped_files=skipped,
        )

    needs_prompt = (not push_all) and (candidates != [("default.env", ".env")])
    if needs_prompt:
        prompter = prompt_fn or _prompt_user_for_file
        selected: list[tuple[str, str]] = []
        try:
            for vault_name, rel_path in existing:
                if prompter(rel_path, f"{final_repo}/{vault_name}"):
                    selected.append((vault_name, rel_path))
        except NonInteractivePromptError as exc:
            return PushResult(False, final_repo, "", message=str(exc), org_name=final_org, skipped_files=skipped)
    else:
        selected = existing

    if not selected:
        return PushResult(
            True, final_repo, "",
            message="No files selected to push.",
            org_name=final_org, skipped_files=skipped, declined_all=True,
        )

    ensure_gitignore(repo_dir)
    pushed: list[PushFileOutcome] = []
    failed: list[PushFileOutcome] = []
    for vault_name, rel_path in selected:
        vault_path = f"{final_repo}/{vault_name}"
        try:
            sha = _encrypt_and_commit(
                repo_root / rel_path, final_org, vault_repo, vault_path, token, recip,
                encrypt_fn=encrypt_fn, commit_fn=commit_fn, filename_override=vault_name,
            )
            pushed.append(PushFileOutcome(vault_name, rel_path, vault_path, True, commit_sha=sha, message="Pushed successfully."))
        except Exception as exc:
            failed.append(PushFileOutcome(vault_name, rel_path, vault_path, False, message=str(exc)))

    if unmapped_root_dotenv and any(o.vault_name == "default.env" and o.rel_path == ".env" for o in pushed):
        new_map = update_env_map_content(raw_map, "default.env", ".env")
        try:
            _commit_env_map_if_changed(com_f, final_org, vault_repo, final_repo, token, raw_map, new_map)
        except Exception as exc:
            failed.append(PushFileOutcome("env.map", "env.map", f"{final_repo}/env.map", False, message=str(exc)))

    target_summary = ", ".join(o.target_path for o in pushed)
    last_sha = pushed[-1].commit_sha if pushed else None
    if failed:
        err_msg = "; ".join(f"{o.rel_path}: {o.message}" for o in failed)
        return PushResult(
            False, final_repo, target_summary, commit_sha=last_sha,
            message=err_msg, org_name=final_org,
            pushed_files=pushed, skipped_files=skipped, failed_files=failed,
        )
    return PushResult(
        True, final_repo, target_summary, commit_sha=last_sha,
        message="Pushed successfully.", org_name=final_org,
        pushed_files=pushed, skipped_files=skipped,
    )


def push_repo_env(
    repo_dir: Path,
    env_file: Path | None = None,
    repo_name: str | None = None,
    org_name: str | None = None,
    gh_token: str | None = None,
    recipient: str | None = None,
    dest_name: str | None = None,
    vault_repo: str | None = None,
    allow_binary: bool = False,
    push_all: bool = False,
    encrypt_fn: Any = None,
    commit_fn: Any = None,
    fetch_fn: Any = None,
    prompt_fn: Any = None,
) -> PushResult:
    """Encrypts local .env file(s), commits to env-store vault, and maintains env.map."""
    from sandbox.env_store import DEFAULT_VAULT_REPO, fetch_github_file

    if push_all and (env_file is not None or dest_name is not None):
        return PushResult(False, repo_name or "", "", message="push_all cannot be combined with env_file or dest_name.")

    final_repo, final_org, token, recip, err = _resolve_repo_context(repo_dir, repo_name, org_name, gh_token, recipient)
    if err or not final_org or not token:
        return PushResult(False, final_repo, "", message=err or "Missing repository credentials.")

    target_vault_repo = vault_repo or DEFAULT_VAULT_REPO
    fetch_f = fetch_fn or fetch_github_file
    com_f = commit_fn or commit_to_env_store

    if env_file is not None or dest_name is not None:
        return _push_single_file(
            repo_dir=repo_dir, env_file=env_file, dest_name=dest_name,
            final_repo=final_repo, final_org=final_org, token=token, recip=recip,
            vault_repo=target_vault_repo, allow_binary=allow_binary,
            encrypt_fn=encrypt_fn, commit_fn=commit_fn, fetch_f=fetch_f, com_f=com_f,
        )
    return _push_from_env_map(
        repo_dir=repo_dir, final_repo=final_repo, final_org=final_org, token=token, recip=recip,
        vault_repo=target_vault_repo, push_all=push_all,
        encrypt_fn=encrypt_fn, commit_fn=commit_fn, fetch_f=fetch_f, com_f=com_f, prompt_fn=prompt_fn,
    )
