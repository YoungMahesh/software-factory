"""Core sandbox lifecycle management, provisioning pipeline, and data schemas."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import modal
from pydantic import BaseModel

from sandbox.config import (
    DEFAULT_METRO_PORT,
    DEFAULT_OPENCODE_PORT,
    DEFAULT_T3_PORT,
    DEFAULT_WEB_PORT,
)
from shared.image import DEFAULT_T3_USAGE_VOLUME


class LaunchRequest(BaseModel):
    repo: str | None = None
    testing: bool = False
    github_branch: str = "main"
    full_clone: bool = False
    name: str | None = None
    from_snapshot: str | None = None
    vm: bool = False
    memory: int | None = None
    no_cloudflare: bool = False
    opencode: bool = False
    opencode_port: int = DEFAULT_OPENCODE_PORT
    t3: bool = False
    t3_port: int = DEFAULT_T3_PORT
    t3_ssh_host: str | None = None
    t3_usage_volume: str = DEFAULT_T3_USAGE_VOLUME
    no_t3_persist: bool = False
    react_native: bool = False
    metro_port: int = DEFAULT_METRO_PORT
    modal: bool = False
    profile: str | None = None
    sops: bool = False
    browser: bool = False
    agy: bool = False
    herdr: bool = False
    pi: bool = False


class LaunchResponse(BaseModel):
    sandbox_id: str
    app_name: str
    sandbox_name: str
    ssh_info: tuple[str, int] | None = None
    ssh_command: str | None = None
    ssh_config: str | None = None
    opencode_url: str | None = None
    opencode_port: int | None = None
    opencode_password: str | None = None
    metro_url: str | None = None
    metro_port: int | None = None
    t3_url: str | None = None
    t3_port: int | None = None
    t3_pair_url: str | None = None
    t3_qr_code: str | None = None
    t3_ssh_host: str | None = None
    t3_persist: bool = False
    t3_usage_volume: str | None = None
    memory_gb: int | None = None
    agy_enabled: bool = False
    cloudflare_enabled: bool = True
    sops_enabled: bool = False
    is_vm: bool = False


class SnapshotRequest(BaseModel):
    sandbox_id: str
    ttl_days: int = 30
    terminate: bool = False
    name: str = ""


class SnapshotResponse(BaseModel):
    sandbox_id: str
    image_id: str
    ttl_days: int
    ttl_seconds: int
    terminated: bool


def validate_launch_request(req: LaunchRequest) -> None:
    """Validates configuration parameters and port assignments.

    Raises ValueError for invalid VM memory, incompatible T3 options, or
    enabled service ports that conflict with each other or the reserved web port.
    Memory, when supplied, must be at least 1 GB and requires a VM.
    """
    if req.memory is not None:
        if not req.vm or req.memory < 1:
            raise ValueError("--memory must be positive GB and can only be used with --vm.")
    if req.t3_ssh_host and not req.t3:
        raise ValueError("--t3-ssh-host can only be used with --t3.")
    if req.no_t3_persist and not req.t3:
        raise ValueError("--no-t3-persist can only be used with --t3.")
    if req.t3_usage_volume != DEFAULT_T3_USAGE_VOLUME and not req.t3:
        raise ValueError("--t3-usage-volume can only be used with --t3.")
    if req.no_t3_persist and req.t3_usage_volume != DEFAULT_T3_USAGE_VOLUME:
        raise ValueError("--no-t3-persist and --t3-usage-volume cannot be used together.")

    ports: list[tuple[str, int]] = []
    if req.opencode:
        ports.append(("--opencode-port", req.opencode_port))
    if req.react_native:
        ports.append(("--metro-port", req.metro_port))
    if req.t3:
        ports.append(("--t3-port", req.t3_port))

    used_ports: dict[int, str] = {}
    for flag, port in ports:
        if port == DEFAULT_WEB_PORT:
            raise ValueError(f"{flag} cannot be {DEFAULT_WEB_PORT}: reserved for Cloudflare Tunnel.")
        if port in used_ports:
            raise ValueError(f"{used_ports[port]} and {flag} must differ: port exposed multiple times.")
        used_ports[port] = flag


def launch_sandbox(
    req: LaunchRequest,
    repo_root: Path | None = None,
    build_image_fn: Callable | None = None,
    load_pubkey_fn: Callable | None = None,
    client: modal.Client | None = None,
    log_cb: Callable[[str], None] | None = None,
    register_ssh_config: bool = False,
    append_ssh_fn: Callable | None = None,
):
    """Provisions a Modal sandbox via SandboxLauncher.

    Retained as a backward-compatible adapter delegating to SandboxLauncher.
    Returns a RunningSandbox tuple-like object providing (sandbox, response).
    """
    from sandbox.launcher import SandboxLauncher

    return SandboxLauncher.run(
        req=req,
        repo_root=repo_root,
        build_image_fn=build_image_fn,
        load_pubkey_fn=load_pubkey_fn,
        append_ssh_fn=append_ssh_fn,
        client=client,
        log_cb=log_cb,
        register_ssh_config=register_ssh_config,
    )


def capture_snapshot_core(
    sandbox_id: str,
    ttl_days: int = 30,
    terminate: bool = False,
    name: str = "",
    profile: str | None = None,
    client: modal.Client | None = None,
) -> SnapshotResponse:
    """Flushes buffers and captures a filesystem snapshot of an active sandbox.

    ttl_days sets the snapshot lifetime in days. If terminate is true, the
    sandbox is terminated after capture. Registry recording is best effort;
    its errors are ignored, while capture and termination errors propagate.
    """
    from sandbox.profiles import get_all_clients, get_client_for_profile

    target_client = client
    target_profile = profile
    if target_client is None:
        if target_profile:
            try:
                target_client = get_client_for_profile(target_profile)
            except Exception:
                target_client = None
        else:
            for prof_name, cli in get_all_clients().items():
                try:
                    sb_probe = modal.Sandbox.from_id(sandbox_id, client=cli)
                    sb_probe.poll()
                    target_client = cli
                    target_profile = prof_name
                    break
                except Exception:
                    pass

    sandbox = (
        modal.Sandbox.from_id(sandbox_id, client=target_client)
        if target_client else modal.Sandbox.from_id(sandbox_id)
    )
    sandbox.exec("sync").wait()

    is_vm = False
    try:
        vm_proc = sandbox.exec("sh", "-c", "[ -S /var/run/docker.sock ] || [ -f /swapfile ]")
        if vm_proc.wait() == 0:
            is_vm = True
    except Exception:
        is_vm = False

    ttl_seconds = ttl_days * 86400
    snapshot_image = sandbox.snapshot_filesystem(ttl=ttl_seconds)
    image_id = snapshot_image.object_id

    try:
        from sandbox.snapshots import record_snapshot
        record_snapshot(
            image_id=image_id, sandbox_id=sandbox_id, name=name,
            ttl_days=ttl_days, is_vm=is_vm, profile=target_profile,
        )
    except Exception:
        pass

    if terminate:
        sandbox.terminate()

    return SnapshotResponse(
        sandbox_id=sandbox_id, image_id=image_id, ttl_days=ttl_days,
        ttl_seconds=ttl_seconds, terminated=terminate,
    )
