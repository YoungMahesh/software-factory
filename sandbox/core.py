"""Core sandbox lifecycle management, provisioning pipeline, and data schemas."""

import json
import os
from pathlib import Path
import secrets
import sys
import time
from typing import Callable
import uuid

import modal
from pydantic import BaseModel

from shared.image import (
    DEFAULT_T3_USAGE_VOLUME,
    REMOTE_STARTUP_SCRIPT,
    SHARED_SECRET_NAME,
    T3_STORAGE_MOUNT_PATH,
    browser_enabled,
    build_sandbox_image,
    get_gradle_volumes,
    get_t3_usage_volumes,
    load_ssh_pub_key,
    resolve_secret_path,
)
from sandbox.config import (
    DEFAULT_METRO_PORT,
    DEFAULT_OPENCODE_PORT,
    DEFAULT_ORG,
    DEFAULT_T3_PORT,
    DEFAULT_WEB_PORT,
    IDLE_TIMEOUT_SECS,
    TIMEOUT_SECS,
)
from sandbox.t3 import setup_t3 as _setup_t3


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
    """Validates configuration parameters and port assignments."""
    if req.memory is not None:
        if not req.vm:
            raise ValueError("--memory can only be used with --vm.")
        if req.memory < 1:
            raise ValueError("--memory must be a positive integer number of GB.")

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

    for flag, port in ports:
        if port == DEFAULT_WEB_PORT:
            raise ValueError(
                f"{flag} cannot be {DEFAULT_WEB_PORT}: port {DEFAULT_WEB_PORT} is reserved for web servers and Cloudflare Tunnel."
            )

    used_ports: dict[int, str] = {}
    for flag, port in ports:
        if port in used_ports:
            raise ValueError(
                f"{used_ports[port]} and {flag} must differ: a port can only be exposed once."
            )
        used_ports[port] = flag


def _resolve_fn(name: str, fallback: Callable) -> Callable:
    main_mod = sys.modules.get("sandbox.main")
    if main_mod and hasattr(main_mod, name):
        return getattr(main_mod, name)
    return fallback


def launch_sandbox(
    req: LaunchRequest,
    repo_root: Path | None = None,
    build_image_fn: Callable | None = None,
    load_pubkey_fn: Callable | None = None,
    client: modal.Client | None = None,
) -> tuple[modal.Sandbox, LaunchResponse]:
    """Provisions a Modal sandbox and executes the post-launch setup pipeline."""
    validate_launch_request(req)

    if repo_root is None:
        if (Path("/root/.secrets") / "github-orgs.env").is_file() or Path("/root/secrets/github-orgs.env").is_file():
            repo_root = Path("/root")
        else:
            repo_root = Path(__file__).resolve().parent.parent

    clean_repo = req.repo.strip().rstrip("/") if req.repo else None
    target_repo, org_name, bare_repo = None, None, None
    orgs_env_file = resolve_secret_path("github-orgs.env", repo_root=repo_root)

    if clean_repo:
        if not orgs_env_file or not orgs_env_file.is_file():
            missing_path = repo_root / "secrets" / "github-orgs.env"
            raise FileNotFoundError(
                f"Organization credentials file not found: {missing_path} (expected .secrets/github-orgs.env or secrets/github-orgs.env)."
            )
        org_name, raw_repo = clean_repo.split("/", 1) if "/" in clean_repo else (DEFAULT_ORG, clean_repo)
        if req.testing:
            org_name = DEFAULT_ORG
            bare_repo = raw_repo if raw_repo.startswith("test-") else f"test-{raw_repo}"
        else:
            bare_repo = raw_repo
        target_repo = f"{org_name}/{bare_repo}"

    pubkey_resolver = load_pubkey_fn or _resolve_fn("load_ssh_pub_key", load_ssh_pub_key)
    pubkey_content = pubkey_resolver()

    random_id = uuid.uuid4().hex[:8]
    app_name = req.name if req.name else (bare_repo if bare_repo else "sandbox")
    sandbox_name = f"{app_name}-{random_id}"
    if client is not None:
        app = modal.App.lookup(app_name, client=client, create_if_missing=True)
    else:
        app = modal.App.lookup(app_name, create_if_missing=True)

    browser_active = browser_enabled(browser=req.browser, opencode=req.opencode, agy=req.agy)

    if req.from_snapshot:
        image = modal.Image.from_id(req.from_snapshot)
    else:
        img_builder = build_image_fn or _resolve_fn("build_sandbox_image", build_sandbox_image)
        image = img_builder(
            opencode=req.opencode,
            agy=req.agy,
            browser=browser_active,
            modal_tooling=req.modal,
            react_native=req.react_native,
            t3=req.t3,
            herdr=req.herdr,
            pi=req.pi,
        )

    if clean_repo and orgs_env_file and orgs_env_file.is_file():
        image = image.add_local_file(orgs_env_file, "/root/.secrets/github-orgs.env", copy=True)

    cloudflare_active = not req.no_cloudflare
    encrypted_ports: list[int] = []
    sandbox_secrets = [modal.Secret.from_name(SHARED_SECRET_NAME)]
    env: dict[str, str | None] = {
        "SSH_AUTHORIZED_KEY": pubkey_content,
        "PORT": str(DEFAULT_WEB_PORT),
        "HOSTNAME": "0.0.0.0",
        "APP_NAME": sandbox_name,
        "MODAL_APP_NAME": app_name,
        "SANDBOX_NAME": sandbox_name,
    }

    if req.from_snapshot:
        env["RESUME_SNAPSHOT"] = "1"
    if clean_repo is None:
        env["NO_REPO"] = "1"
    if target_repo:
        env["GH_REPO"] = target_repo
    if org_name:
        env["GH_ORG"] = org_name
    if req.full_clone:
        env["FULL_CLONE"] = "1"
    if not cloudflare_active:
        env["ENABLE_CLOUDFLARE"] = "0"

    memory_gb: int | None = None
    if req.vm:
        memory_gb = req.memory if req.memory is not None else None
        env["SWAP_GB"] = str(memory_gb * 2 if memory_gb else 2)
        env["ENABLE_DOCKER"] = "1"

    opencode_password = None
    if req.opencode:
        encrypted_ports.append(req.opencode_port)
        opencode_password = secrets.token_urlsafe(16)
        sandbox_secrets.append(modal.Secret.from_dict({"OPENCODE_SERVER_PASSWORD": opencode_password}))
        env["ENABLE_OPENCODE"] = "1"
        env["OPENCODE_PORT"] = str(req.opencode_port)

    t3_persist_enabled = req.t3 and not req.no_t3_persist
    t3_ssh_alias = req.t3_ssh_host or sandbox_name
    if req.t3:
        encrypted_ports.append(req.t3_port)
        env["ENABLE_T3"] = "1"
        env["T3_PORT"] = str(req.t3_port)
        env["FLAGS_enforce_kernel_ipv6_support"] = "false"
        env["T3_SSH_HOST"] = t3_ssh_alias
        if t3_persist_enabled:
            env["ENABLE_T3_PERSISTENCE"] = "1"
            env["T3_USAGE_VOLUME"] = req.t3_usage_volume
            env["ANTIGRAVITY_DATA_DIR"] = f"{T3_STORAGE_MOUNT_PATH}/conversations"

    for flag, key in [
        (req.agy, "ENABLE_ANTIGRAVITY"),
        (req.modal, "ENABLE_MODAL"),
        (req.sops, "ENABLE_SOPS"),
        (req.herdr, "ENABLE_HERDR"),
        (req.pi, "ENABLE_PI"),
        (browser_active, "ENABLE_BROWSER"),
    ]:
        if flag:
            env[key] = "1"

    volumes = {}
    if t3_persist_enabled:
        volumes.update(get_t3_usage_volumes(req.t3_usage_volume))
    if req.react_native:
        encrypted_ports.append(req.metro_port)
        env["ENABLE_REACT_NATIVE"] = "1"
        env["METRO_PORT"] = str(req.metro_port)
        volumes.update(get_gradle_volumes())

    feature_flags = [
        (not req.no_cloudflare, "Cloudflare Tunnel"),
        (req.full_clone, "Full Git Clone"),
        (req.react_native, "React Native"),
        (req.agy, "Antigravity"),
        (req.opencode, "OpenCode"),
        (req.t3, "T3 Code"),
        (t3_persist_enabled, "T3 Usage Persistence"),
        (req.modal, "Modal"),
        (req.sops, "SOPS"),
        (req.herdr, "Herdr"),
        (req.pi, "Pi"),
        (browser_active, "Browser"),
    ]
    features = [label for active, label in feature_flags if active]

    runtime_desc = "VM Sandbox" if req.vm else "Sandbox"
    features_suffix = f" & {' & '.join(features)}" if features else ""
    from_suffix = f" from snapshot {req.from_snapshot}" if req.from_snapshot else ""
    print(
        f"🏝️  Launching Modal {runtime_desc}{from_suffix} with SSH"
        f"{features_suffix} (App: {app_name}, Sandbox: {sandbox_name})..."
    )

    sandbox_kwargs: dict = {
        "timeout": TIMEOUT_SECS,
        "idle_timeout": IDLE_TIMEOUT_SECS,
        "image": image,
        "app": app,
        "name": sandbox_name,
        "tags": {"instance_name": sandbox_name, "app_name": app_name},
        "volumes": volumes,
        "unencrypted_ports": [22],
        "encrypted_ports": encrypted_ports,
        "cpu": (0.125, 4.0),
        "env": env,
        "runtime": "vm" if req.vm else "gvisor",
        "memory": (128, 16384),
    }
    if client is not None:
        sandbox_kwargs["client"] = client

    with modal.enable_output():
        sandbox = modal.Sandbox.create(
            "bash",
            REMOTE_STARTUP_SCRIPT,
            req.github_branch,
            secrets=sandbox_secrets,
            **sandbox_kwargs,
        )

    ssh_info, opencode_url, metro_url, t3_url = None, None, None, None
    try:
        tunnels = sandbox.tunnels()
        if 22 in tunnels:
            ssh_info = tunnels[22].tcp_socket
        if req.opencode and req.opencode_port in tunnels:
            opencode_url = tunnels[req.opencode_port].url
        if req.react_native and req.metro_port in tunnels:
            metro_url = tunnels[req.metro_port].url
        if req.t3 and req.t3_port in tunnels:
            t3_url = tunnels[req.t3_port].url
    except Exception as exc:
        print(f"⚠️  Could not obtain tunnel metadata: {exc}", file=sys.stderr)

    t3_pair_url, t3_qr_code = None, None
    if req.t3 and t3_url:
        t3_pair_url, t3_qr_code = _setup_t3(sandbox, t3_url, t3_ssh_alias)

    ssh_cmd = (
        f"ssh -i ~/.ssh/modal-sandbox -o StrictHostKeyChecking=no -p {ssh_info[1]} root@{ssh_info[0]}"
        if ssh_info
        else f"modal shell {sandbox.object_id}"
    )

    try:
        from sandbox.lifecycle import record_sandbox_connection_info

        record_sandbox_connection_info(
            sandbox.object_id,
            ssh_command=ssh_cmd,
            t3_pair_url=t3_pair_url,
            has_t3=bool(req.t3),
        )
    except Exception:
        pass

    response = LaunchResponse(
        sandbox_id=sandbox.object_id,
        app_name=app_name,
        sandbox_name=sandbox_name,
        ssh_info=ssh_info,
        ssh_command=ssh_cmd,
        opencode_url=opencode_url,
        opencode_port=req.opencode_port if req.opencode else None,
        opencode_password=opencode_password,
        metro_url=metro_url,
        metro_port=req.metro_port if req.react_native else None,
        t3_url=t3_url,
        t3_port=req.t3_port if req.t3 else None,
        t3_pair_url=t3_pair_url,
        t3_qr_code=t3_qr_code,
        t3_ssh_host=t3_ssh_alias,
        t3_persist=t3_persist_enabled,
        t3_usage_volume=req.t3_usage_volume if t3_persist_enabled else None,
        memory_gb=memory_gb,
        agy_enabled=req.agy,
        cloudflare_enabled=cloudflare_active,
        sops_enabled=req.sops,
        is_vm=req.vm,
    )
    return sandbox, response


def capture_snapshot_core(
    sandbox_id: str,
    ttl_days: int = 30,
    terminate: bool = False,
    name: str = "",
    profile: str | None = None,
    client: modal.Client | None = None,
) -> SnapshotResponse:
    """Flushes buffers and captures a filesystem snapshot of an active sandbox."""
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
            # Discover which profile has access to sandbox_id
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
        if target_client
        else modal.Sandbox.from_id(sandbox_id)
    )
    sync_proc = sandbox.exec("sync")
    sync_proc.wait()

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
            image_id=image_id,
            sandbox_id=sandbox_id,
            name=name,
            ttl_days=ttl_days,
            is_vm=is_vm,
            profile=target_profile,
        )
    except Exception:
        pass

    if terminate:
        sandbox.terminate()

    return SnapshotResponse(
        sandbox_id=sandbox_id,
        image_id=image_id,
        ttl_days=ttl_days,
        ttl_seconds=ttl_seconds,
        terminated=terminate,
    )
