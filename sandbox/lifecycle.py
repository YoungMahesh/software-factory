"""Modal Sandbox Lifecycle and Inspection Services.

Provides functions to discover, inspect, and terminate running sandboxes
across Modal Apps, environments, and multi-tenant workspace profiles.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import modal

from sandbox.profiles import get_active_profile_name, get_all_clients, get_client_for_profile

logger = logging.getLogger(__name__)

_SANDBOX_METADATA_CACHE: dict[str, dict[str, Any]] = {}


def record_sandbox_connection_info(
    sandbox_id: str,
    ssh_command: str | None = None,
    t3_pair_url: str | None = None,
    has_t3: bool = False,
) -> None:
    """Pre-populates or updates connection metadata in cache for a sandbox."""
    _SANDBOX_METADATA_CACHE[sandbox_id] = {
        "ssh_command": ssh_command or f"modal shell {sandbox_id}",
        "t3_pair_url": t3_pair_url,
        "has_t3": has_t3,
    }


def clear_sandbox_metadata_cache(sandbox_id: str | None = None) -> None:
    """Clears cached connection metadata for a specific sandbox or entirely."""
    if sandbox_id:
        _SANDBOX_METADATA_CACHE.pop(sandbox_id, None)
    else:
        _SANDBOX_METADATA_CACHE.clear()


def resolve_sandbox_connection_info(sb: modal.Sandbox) -> tuple[str | None, str | None]:
    """Resolves ssh_command and t3_pair_url for an active sandbox container with in-memory caching."""
    cached = _SANDBOX_METADATA_CACHE.get(sb.object_id)
    if cached:
        t3_pair = cached.get("t3_pair_url")
        if t3_pair and "#token=" in t3_pair:
            return cached.get("ssh_command"), t3_pair
        if cached.get("ssh_command") and not cached.get("has_t3"):
            return cached.get("ssh_command"), None

    ssh_command = None
    t3_pair_url = None
    has_t3 = False

    try:
        tunnels = sb.tunnels(timeout=2) if hasattr(sb, "tunnels") else {}
        if tunnels and 22 in tunnels:
            tcp_sock = getattr(tunnels[22], "tcp_socket", None)
            if tcp_sock:
                ssh_host, ssh_port = tcp_sock
                ssh_command = (
                    f"ssh -i ~/.ssh/modal-sandbox -o StrictHostKeyChecking=no -p {ssh_port} root@{ssh_host}"
                )

        if tunnels and 3775 in tunnels:
            has_t3 = True
            t3_tunnel_url = getattr(tunnels[3775], "url", None)
            if t3_tunnel_url:
                clean_url = t3_tunnel_url.rstrip("/")
                if hasattr(sb, "exec"):
                    try:
                        proc = sb.exec("cat", "/tmp/t3-pairing.json")
                        if proc.wait() == 0:
                            data = json.loads(proc.stdout.read().strip())
                            token = data.get("credential")
                            if token:
                                t3_pair_url = f"{clean_url}/pair#token={token}"
                    except Exception:
                        pass
                if not t3_pair_url:
                    t3_pair_url = clean_url
    except Exception as exc:
        logger.debug("Failed resolving tunnels for %s: %s", sb.object_id, exc)

    if not ssh_command:
        ssh_command = f"modal shell {sb.object_id}"

    _SANDBOX_METADATA_CACHE[sb.object_id] = {
        "ssh_command": ssh_command,
        "t3_pair_url": t3_pair_url,
        "has_t3": has_t3,
    }
    return ssh_command, t3_pair_url


def resolve_instance_name(sb: modal.Sandbox) -> str | None:
    """Attempts to resolve the instance name configured inside the sandbox container."""
    tags = sb.get_tags() if hasattr(sb, "get_tags") else {}
    if "instance_name" in tags:
        return tags["instance_name"]
    if "name" in tags:
        return tags["name"]

    try:
        proc = sb.exec("cat", "/tmp/agy-remote-control.log")
        out = proc.stdout.read()
        for line in out.splitlines():
            if "Instance name set to" in line and '"' in line:
                return line.split('"')[1]
    except Exception:
        pass

    try:
        proc = sb.exec("cat", "/root/.gemini/config/config.json")
        data = json.loads(proc.stdout.read())
        cfg_name = data.get("userSettings", {}).get("cliRemoteControlHostname")
        if cfg_name:
            return cfg_name
    except Exception:
        pass

    try:
        proc = sb.exec("printenv")
        out = proc.stdout.read()
        env_dict = {}
        for line in out.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                env_dict[k] = v
        if "SANDBOX_NAME" in env_dict:
            return env_dict["SANDBOX_NAME"]
        if "APP_NAME" in env_dict:
            return env_dict["APP_NAME"]
    except Exception:
        pass

    return None


def resolve_app_name(sb: modal.Sandbox, fallback: str | None = None) -> str | None:
    """Attempts to resolve the logical Modal App name or ID for a sandbox."""
    tags = sb.get_tags() if hasattr(sb, "get_tags") else {}
    if "app_name" in tags:
        return tags["app_name"]

    try:
        proc = sb.exec("printenv", "MODAL_APP_NAME")
        out = proc.stdout.read().strip()
        if out:
            return out
    except Exception:
        pass

    return fallback


def _query_profile_sandboxes(
    client: modal.Client,
    profile_name: str,
    app_name: str | None,
    all_apps: bool,
) -> list[dict[str, Any]]:
    """Queries sandboxes for a single profile client."""
    target_app = app_name
    if not all_apps and target_app is None:
        target_app = "software-factory"

    app_id = None
    if target_app and not all_apps:
        try:
            app = modal.App.lookup(target_app, client=client)
            app_id = app.app_id
        except Exception as exc:
            logger.debug(
                "App '%s' not found for profile '%s': %s", target_app, profile_name, exc
            )
            return []

    try:
        sb_generator = (
            modal.Sandbox.list(app_id=app_id, client=client)
            if app_id
            else modal.Sandbox.list(client=client)
        )
    except Exception as exc:
        logger.warning(
            "Failed listing sandboxes under profile '%s': %s", profile_name, exc
        )
        return []

    sandboxes: list[dict[str, Any]] = []
    for sb in sb_generator:
        poll_code = sb.poll()
        is_running = poll_code is None
        if is_running:
            name = resolve_instance_name(sb)
            ssh_command, t3_pair_url = resolve_sandbox_connection_info(sb)
        else:
            name = None
            ssh_command = None
            t3_pair_url = None
            _SANDBOX_METADATA_CACHE.pop(sb.object_id, None)

        app_id_fallback = getattr(sb, "app_id", getattr(sb, "_app_id", None))
        app_label = target_app
        if all_apps or not app_label:
            resolved = resolve_app_name(sb, fallback=app_id_fallback) if is_running else app_id_fallback
            app_label = resolved or target_app
        sandboxes.append({
            "id": sb.object_id,
            "name": name,
            "running": is_running,
            "exit_code": poll_code,
            "app_name": app_label,
            "profile": profile_name,
            "ssh_command": ssh_command,
            "t3_pair_url": t3_pair_url,
        })
    return sandboxes


def get_sandboxes(
    app_name: str | None = "software-factory",
    all_apps: bool = False,
    profile: str | None = None,
) -> list[dict[str, Any]]:
    """Fetches and inspects active Modal sandboxes scoped or aggregated across profiles."""
    if profile == "all":
        all_clients = get_all_clients()
        aggregated: list[dict[str, Any]] = []
        for prof_name, client in all_clients.items():
            try:
                sandboxes = _query_profile_sandboxes(client, prof_name, app_name, all_apps)
                aggregated.extend(sandboxes)
            except Exception as exc:
                logger.warning(
                    "Error aggregating sandboxes for profile '%s': %s", prof_name, exc
                )
        return aggregated

    target_profile = profile or get_active_profile_name()
    try:
        client = get_client_for_profile(target_profile)
        return _query_profile_sandboxes(client, target_profile or "default", app_name, all_apps)
    except Exception as exc:
        logger.error("Failed to query sandboxes for profile '%s': %s", target_profile, exc)
        return []


def terminate_sandbox(sandbox_id: str, profile: str | None = None) -> dict[str, Any]:
    """Terminates a single sandbox by object ID, using the matching profile client."""
    if profile and profile != "all":
        try:
            client = get_client_for_profile(profile)
            sb = modal.Sandbox.from_id(sandbox_id, client=client)
            sb.terminate(wait=True)
            clear_sandbox_metadata_cache(sandbox_id)
            return {
                "id": sandbox_id,
                "status": "terminated",
                "exit_code": sb.poll(),
                "profile": profile,
            }
        except Exception as exc:
            logger.error(
                "Failed to terminate sandbox %s with profile %s: %s",
                sandbox_id,
                profile,
                exc,
            )
            return {
                "id": sandbox_id,
                "status": "error",
                "error": str(exc),
                "profile": profile,
            }

    # First attempt termination with active profile
    active_profile = get_active_profile_name()
    if active_profile:
        try:
            client = get_client_for_profile(active_profile)
            sb = modal.Sandbox.from_id(sandbox_id, client=client)
            sb.terminate(wait=True)
            clear_sandbox_metadata_cache(sandbox_id)
            return {
                "id": sandbox_id,
                "status": "terminated",
                "exit_code": sb.poll(),
                "profile": active_profile,
            }
        except Exception as exc:
            logger.debug(
                "Active profile %s terminate probe failed: %s; trying other profiles",
                active_profile,
                exc,
            )

    # Attempt termination across remaining configured profiles
    all_clients = get_all_clients()
    last_error: Exception | None = None
    for prof_name, client in all_clients.items():
        if prof_name == active_profile:
            continue
        try:
            sb = modal.Sandbox.from_id(sandbox_id, client=client)
            sb.terminate(wait=True)
            clear_sandbox_metadata_cache(sandbox_id)
            return {
                "id": sandbox_id,
                "status": "terminated",
                "exit_code": sb.poll(),
                "profile": prof_name,
            }
        except Exception as exc:
            last_error = exc
            logger.debug(
                "Sandbox %s termination probe failed under profile %s: %s",
                sandbox_id,
                prof_name,
                exc,
            )

    error_msg = str(last_error) if last_error else "Sandbox not found in any profile"
    return {
        "id": sandbox_id,
        "status": "error",
        "error": error_msg,
    }


def terminate_sandboxes(
    target_ids: list[str],
    dry_run: bool = False,
    profile: str | None = None,
) -> list[dict[str, Any]]:
    """Terminates multiple sandboxes by their object ID."""
    results = []
    for sb_id in target_ids:
        if dry_run:
            results.append({"id": sb_id, "status": "dry-run", "exit_code": None})
            continue

        results.append(terminate_sandbox(sb_id, profile=profile))
    return results
