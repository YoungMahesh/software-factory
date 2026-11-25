"""Idempotent backup and restore orchestration for Host Ingress Store (caddy-store)."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import subprocess
from typing import Any
import uuid

from sandbox.config import parse_env_file, resolve_factory_root
from sandbox.env_store import resolve_gh_token
from sandbox.infra_deploy import VpsSshConfig, build_ssh_cmd

from ._compose_filter import filter_compose_override_networks
from ._github import (
    CANONICAL_CADDY_STORE_REPO,
    DEFAULT_CADDY_STORE_PROFILE,
    PROFILE_NAME_RE,
    commit_caddy_store_file,
    delete_caddy_store_file,
    ensure_caddy_store_repo,
    fetch_caddy_store_bundle,
    git_blob_sha,
    list_caddy_store_profile_blobs,
)
from ._vps import (
    DEFAULT_CADDY_DIR,
    apply_files_to_vps,
    build_tar_gz_bytes,
    fetch_vps_caddy_files,
    list_remote_docker_networks,
    read_local_caddy_dir,
    write_local_caddy_dir,
)


@dataclass
class CaddyStoreResult:
    """Outcome of a Host Ingress Store backup or restore operation."""

    success: bool
    profile: str
    message: str
    changed: bool = False
    skipped_networks: list[str] = field(default_factory=list)
    files_written: list[str] = field(default_factory=list)
    files_deleted: list[str] = field(default_factory=list)


def resolve_caddy_store_profile(
    profile: str | None = None,
    dotenv: dict[str, str] | None = None,
) -> str:
    """Resolves and validates the logical VPS profile folder name."""
    raw = (
        profile
        or os.environ.get("CADDY_STORE_PROFILE")
        or (dotenv or {}).get("CADDY_STORE_PROFILE")
        or DEFAULT_CADDY_STORE_PROFILE
    ).strip()
    if not PROFILE_NAME_RE.match(raw):
        raise ValueError(
            f"Invalid Caddy store profile '{raw}'. Use 1-64 alphanumeric, '.', '_', or '-' characters."
        )
    return raw


def _resolve_gh_context(
    org_name: str | None,
    gh_token: str | None,
    dotenv: dict[str, str],
) -> tuple[str | None, str | None]:
    owner = org_name or os.environ.get("GH_ORG_NAME") or dotenv.get("GH_ORG_NAME")
    token = resolve_gh_token(gh_token or dotenv.get("GH_TOKEN") or dotenv.get("GITHUB_TOKEN"))
    return owner, token


def _format_skip_note(skipped_nets: list[str]) -> str:
    return f" Skipped missing external networks: {', '.join(skipped_nets)}." if skipped_nets else ""


def backup_caddy_to_store(
    vps_config: VpsSshConfig | None = None,
    *,
    profile: str | None = None,
    org_name: str | None = None,
    gh_token: str | None = None,
    dir_out: Path | None = None,
    from_dir: Path | None = None,
    caddy_dir: str = DEFAULT_CADDY_DIR,
) -> CaddyStoreResult:
    """Captures declarative /opt/caddy config from VPS (or --from-dir) and mirrors to caddy-store."""
    root = resolve_factory_root()
    dotenv = parse_env_file(root / ".env") if (root / ".env").is_file() else {}
    resolved_profile = resolve_caddy_store_profile(profile, dotenv=dotenv)
    owner, token = _resolve_gh_context(org_name, gh_token, dotenv)
    if not owner:
        return CaddyStoreResult(False, resolved_profile, "Missing GH_ORG_NAME in environment or .env.")
    if not token:
        return CaddyStoreResult(False, resolved_profile, "Missing GH_TOKEN / GITHUB_TOKEN / gh CLI auth.")

    if from_dir is not None:
        source_files = read_local_caddy_dir(from_dir)
    else:
        if vps_config is None:
            raise ValueError("vps_config is required when --from-dir is not provided.")
        source_files = fetch_vps_caddy_files(vps_config, caddy_dir=caddy_dir)

    if not source_files:
        return CaddyStoreResult(
            False, resolved_profile, f"No declarative Caddy configuration found in {from_dir or caddy_dir}."
        )
    if dir_out is not None:
        write_local_caddy_dir(dir_out, source_files)

    ensure_caddy_store_repo(owner, token, create_if_missing=True)
    remote_blobs = list_caddy_store_profile_blobs(owner, resolved_profile, token)

    to_upsert = {
        rel: content
        for rel, content in source_files.items()
        if remote_blobs.get(rel) != git_blob_sha(content.encode("utf-8"))
    }
    to_delete = sorted(rel for rel in remote_blobs if rel not in source_files)

    if not to_upsert and not to_delete:
        return CaddyStoreResult(
            True,
            resolved_profile,
            f"Host Ingress Store '{owner}/{CANONICAL_CADDY_STORE_REPO}' profile '{resolved_profile}' is already up to date (idempotent no-op).",
            changed=False,
        )

    for rel, content in sorted(to_upsert.items()):
        commit_caddy_store_file(
            owner,
            f"{resolved_profile}/{rel}",
            content.encode("utf-8"),
            token,
            commit_message=f"chore(caddy-store/{resolved_profile}): update {rel}",
            sha=remote_blobs.get(rel),
        )
    for rel in to_delete:
        delete_caddy_store_file(
            owner,
            f"{resolved_profile}/{rel}",
            remote_blobs[rel],
            token,
            commit_message=f"chore(caddy-store/{resolved_profile}): remove {rel}",
        )

    return CaddyStoreResult(
        True,
        resolved_profile,
        f"Backed up {len(to_upsert)} updated and {len(to_delete)} removed file(s) to '{owner}/{CANONICAL_CADDY_STORE_REPO}' (profile '{resolved_profile}').",
        changed=True,
        files_written=sorted(to_upsert),
        files_deleted=to_delete,
    )


def _bootstrap_restore_vps(
    vps_config: VpsSshConfig,
    cfg: Any,
    store_files: dict[str, str],
    filtered_override: str | None,
    skipped_nets: list[str],
    resolved_profile: str,
    owner_label: str,
) -> CaddyStoreResult:
    from sandbox.caddy_deploy import (
        check_ports_available,
        ensure_docker_network,
        find_caddy_source_dir,
        validate_caddy,
    )

    ports_ok, ports_msg = check_ports_available(vps_config)
    if not ports_ok:
        return CaddyStoreResult(False, resolved_profile, ports_msg)
    net_ok, net_msg = ensure_docker_network(vps_config, cfg.network)
    if not net_ok:
        return CaddyStoreResult(False, resolved_profile, net_msg)

    src = find_caddy_source_dir()
    to_write = {k: v for k, v in store_files.items() if k.startswith("conf/")}
    to_write.setdefault("conf/Caddyfile", (src / "conf" / "Caddyfile").read_text(encoding="utf-8"))
    if filtered_override is not None:
        to_write["docker-compose.override.yml"] = filtered_override

    compose_payload = build_tar_gz_bytes(
        {"docker-compose.yml": (src / "docker-compose.yml").read_text(encoding="utf-8"), **to_write}
    )
    p_write = subprocess.run(
        build_ssh_cmd(vps_config, f"mkdir -p '{cfg.caddy_dir}/conf/sites' && tar -xzf - -C '{cfg.caddy_dir}'"),
        input=compose_payload, timeout=45, capture_output=True, check=False,
    )
    if p_write.returncode != 0:
        err = p_write.stderr.decode("utf-8", errors="replace").strip()
        return CaddyStoreResult(False, resolved_profile, f"Failed writing {cfg.caddy_dir}: {err}")

    up_res = subprocess.run(
        build_ssh_cmd(vps_config, f"cd '{cfg.caddy_dir}' && docker compose up -d"),
        timeout=120, capture_output=True, text=True, check=False,
    )
    if up_res.returncode != 0:
        return CaddyStoreResult(
            False, resolved_profile, f"Failed starting {cfg.caddy_dir}: {up_res.stderr.strip() or up_res.stdout.strip()}"
        )

    val_ok, val_msg = validate_caddy(vps_config, cfg)
    if not val_ok:
        return CaddyStoreResult(
            False, resolved_profile, f"Bootstrapped {cfg.caddy_dir}, but validation failed: {val_msg}",
            skipped_networks=skipped_nets,
        )
    return CaddyStoreResult(
        True,
        resolved_profile,
        f"Bootstrapped and restored {cfg.caddy_dir} from '{owner_label}' (profile '{resolved_profile}').{_format_skip_note(skipped_nets)}",
        changed=True,
        skipped_networks=skipped_nets,
        files_written=sorted(to_write),
    )


def _converge_running_vps(
    vps_config: VpsSshConfig,
    cfg: Any,
    store_files: dict[str, str],
    filtered_override: str | None,
    has_store_override: bool,
    skipped_nets: list[str],
    resolved_profile: str,
    owner_label: str,
    prune: bool,
) -> CaddyStoreResult:
    from sandbox.caddy_deploy import ensure_caddy_network, reload_caddy, validate_caddy

    net_ok, net_msg = ensure_caddy_network(vps_config, cfg)
    if not net_ok:
        return CaddyStoreResult(False, resolved_profile, net_msg)

    current_files = fetch_vps_caddy_files(vps_config, caddy_dir=cfg.caddy_dir)
    conf_to_write = {
        rel: content for rel, content in store_files.items()
        if rel.startswith("conf/") and current_files.get(rel) != content
    }
    conf_to_prune = (
        sorted(rel for rel in current_files if rel.startswith("conf/") and rel != "conf/Caddyfile" and rel not in store_files)
        if prune
        else []
    )
    override_write: str | None = None
    override_delete = False
    if filtered_override is not None:
        if current_files.get("docker-compose.override.yml") != filtered_override:
            override_write = filtered_override
    elif "docker-compose.override.yml" in current_files and (has_store_override or prune):
        override_delete = True

    if not conf_to_write and not conf_to_prune and override_write is None and not override_delete:
        return CaddyStoreResult(
            True,
            resolved_profile,
            f"Host Ingress Proxy at {cfg.caddy_dir} is already up to date with profile '{resolved_profile}' (idempotent no-op).{_format_skip_note(skipped_nets)}",
            changed=False,
            skipped_networks=skipped_nets,
        )

    bak_dir = f"/tmp/caddy-restore-bak-{uuid.uuid4().hex[:8]}"
    subprocess.run(
        build_ssh_cmd(
            vps_config,
            f"mkdir -p '{bak_dir}' && ([ -d '{cfg.caddy_dir}/conf' ] && cp -a '{cfg.caddy_dir}/conf' '{bak_dir}/conf' || true) && "
            f"([ -f '{cfg.caddy_dir}/docker-compose.override.yml' ] && cp -a '{cfg.caddy_dir}/docker-compose.override.yml' '{bak_dir}/docker-compose.override.yml' || true)",
        ),
        timeout=20, capture_output=True, check=False,
    )

    def _rollback() -> None:
        subprocess.run(
            build_ssh_cmd(
                vps_config,
                f"if [ -d '{bak_dir}/conf' ]; then rm -rf '{cfg.caddy_dir}/conf' && cp -a '{bak_dir}/conf' '{cfg.caddy_dir}/conf'; fi; "
                f"if [ -f '{bak_dir}/docker-compose.override.yml' ]; then cp -a '{bak_dir}/docker-compose.override.yml' '{cfg.caddy_dir}/docker-compose.override.yml'; "
                f"else rm -f '{cfg.caddy_dir}/docker-compose.override.yml'; fi; rm -rf '{bak_dir}'",
            ),
            timeout=30, capture_output=True, check=False,
        )

    try:
        if conf_to_write or conf_to_prune:
            apply_files_to_vps(vps_config, conf_to_write, conf_to_prune, caddy_dir=cfg.caddy_dir)
            val_ok, val_msg = validate_caddy(vps_config, cfg)
            if not val_ok:
                _rollback()
                return CaddyStoreResult(
                    False, resolved_profile, f"Validation failed (rolled back): {val_msg}", skipped_networks=skipped_nets
                )

        if override_write is not None or override_delete:
            apply_files_to_vps(
                vps_config,
                {"docker-compose.override.yml": override_write} if override_write is not None else {},
                ["docker-compose.override.yml"] if override_delete else [],
                caddy_dir=cfg.caddy_dir,
            )
            up_res = subprocess.run(
                build_ssh_cmd(vps_config, f"cd '{cfg.caddy_dir}' && docker compose up -d"),
                timeout=120, capture_output=True, text=True, check=False,
            )
            if up_res.returncode != 0:
                _rollback()
                subprocess.run(build_ssh_cmd(vps_config, f"cd '{cfg.caddy_dir}' && docker compose up -d"), timeout=120, capture_output=True, check=False)
                return CaddyStoreResult(
                    False, resolved_profile, f"Docker Compose network convergence failed (rolled back): {up_res.stderr.strip() or up_res.stdout.strip()}"
                )
        else:
            rel_ok, rel_msg = reload_caddy(vps_config, cfg)
            if not rel_ok:
                _rollback()
                return CaddyStoreResult(
                    False, resolved_profile, f"Reload failed (rolled back): {rel_msg}", skipped_networks=skipped_nets
                )
    finally:
        subprocess.run(build_ssh_cmd(vps_config, f"rm -rf '{bak_dir}'"), timeout=15, capture_output=True, check=False)

    written = sorted(list(conf_to_write) + (["docker-compose.override.yml"] if override_write is not None else []))
    deleted = sorted(conf_to_prune + (["docker-compose.override.yml"] if override_delete else []))
    return CaddyStoreResult(
        True,
        resolved_profile,
        f"Restored {len(written)} updated and {len(deleted)} removed file(s) from '{owner_label}' (profile '{resolved_profile}') to {cfg.caddy_dir}.{_format_skip_note(skipped_nets)}",
        changed=True,
        skipped_networks=skipped_nets,
        files_written=written,
        files_deleted=deleted,
    )


def restore_caddy_from_store(
    vps_config: VpsSshConfig,
    *,
    profile: str | None = None,
    org_name: str | None = None,
    gh_token: str | None = None,
    prune: bool = False,
    bootstrap: bool = False,
    dir_out: Path | None = None,
    from_dir: Path | None = None,
    caddy_dir: str = DEFAULT_CADDY_DIR,
) -> CaddyStoreResult:
    """Restores Host Ingress Proxy configuration from caddy-store (or --from-dir) onto VPS."""
    from sandbox.caddy_deploy import CaddyConfig, check_caddy_running

    root = resolve_factory_root()
    dotenv = parse_env_file(root / ".env") if (root / ".env").is_file() else {}
    resolved_profile = resolve_caddy_store_profile(profile, dotenv=dotenv)

    if from_dir is not None:
        store_files = read_local_caddy_dir(from_dir)
        owner_label = str(from_dir)
    else:
        owner, token = _resolve_gh_context(org_name, gh_token, dotenv)
        if not owner:
            return CaddyStoreResult(False, resolved_profile, "Missing GH_ORG_NAME in environment or .env.")
        if not token:
            return CaddyStoreResult(False, resolved_profile, "Missing GH_TOKEN / GITHUB_TOKEN / gh CLI auth.")
        ensure_caddy_store_repo(owner, token, create_if_missing=False)
        store_files = fetch_caddy_store_bundle(owner, resolved_profile, token)
        owner_label = f"{owner}/{CANONICAL_CADDY_STORE_REPO}"

    if not store_files:
        return CaddyStoreResult(
            False, resolved_profile, f"No declarative Caddy files found for profile '{resolved_profile}' in '{owner_label}'."
        )
    if dir_out is not None:
        write_local_caddy_dir(dir_out, store_files)

    cfg = CaddyConfig(caddy_dir=caddy_dir)
    running, run_msg = check_caddy_running(vps_config, cfg)
    existing_nets = list_remote_docker_networks(vps_config)

    raw_override = store_files.get("docker-compose.override.yml")
    filtered_override: str | None = None
    skipped_nets: list[str] = []
    if raw_override is not None:
        filtered_override, skipped_nets = filter_compose_override_networks(
            raw_override, existing_nets, {cfg.network}
        )

    if not running:
        if not bootstrap:
            return CaddyStoreResult(
                False, resolved_profile, f"{run_msg} Re-run with --bootstrap to provision {caddy_dir}."
            )
        return _bootstrap_restore_vps(
            vps_config, cfg, store_files, filtered_override, skipped_nets, resolved_profile, owner_label
        )

    return _converge_running_vps(
        vps_config, cfg, store_files, filtered_override, raw_override is not None,
        skipped_nets, resolved_profile, owner_label, prune,
    )
