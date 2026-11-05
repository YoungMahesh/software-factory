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
    REMOTE_STARTUP_SCRIPT,
    SHARED_SECRET_NAME,
    browser_enabled,
    build_sandbox_image,
    get_gradle_volumes,
    load_ssh_pub_key,
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
from sandbox.cli import generate_ascii_qr


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
    memory_gb: int | None = None
    agy_enabled: bool = False
    cloudflare_enabled: bool = True
    sops_enabled: bool = False
    is_vm: bool = False


class SnapshotRequest(BaseModel):
    sandbox_id: str
    ttl_days: int = 30
    terminate: bool = False


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


def _setup_t3(sandbox: modal.Sandbox, t3_url: str, ssh_host: str) -> tuple[str | None, str | None]:
    clean_url = t3_url.rstrip("/")
    try:
        cfg = (
            f"import json, os, time\nurl = {json.dumps(clean_url)}\nhost = {json.dumps(ssh_host)}\n"
            "os.makedirs('/root/.t3', exist_ok=True)\n"
            "open('/root/.t3/public_url', 'w').write(url + '\\n')\n"
            "try:\n open('/etc/machine-info', 'w').write(f'PRETTY_HOSTNAME=\"{host}\"\\n')\n"
            "except Exception: pass\n"
            "for p in ['/etc/environment', '/root/.bashrc']:\n"
            " try:\n"
            "  c = open(p).read() if os.path.exists(p) else ''\n"
            "  with open(p, 'a+') as f:\n"
            "   if 'T3_PUBLIC_URL=' not in c: f.write(f'export T3_PUBLIC_URL=\"{url}\"\\n')\n"
            "   if 'T3_SSH_HOST=' not in c: f.write(f'export T3_SSH_HOST=\"{host}\"\\n')\n"
            " except Exception: pass\n"
            "rt = '/root/.t3/userdata/server-runtime.json'\n"
            "for _ in range(20):\n"
            " if os.path.isfile(rt):\n"
            "  try:\n"
            "   d = json.load(open(rt))\n"
            "   if d.get('devUrl') != url:\n"
            "    d['devUrl'] = url\n"
            "    json.dump(d, open(rt + '.tmp', 'w'), indent=2)\n"
            "    os.replace(rt + '.tmp', rt)\n"
            "   break\n"
            "  except Exception: pass\n"
            " time.sleep(0.25)\n"
        )
        sandbox.exec("python3", "-c", cfg).wait()
    except Exception:
        pass

    pair_url, qr_code = None, None
    try:
        p = sandbox.exec("t3", "auth", "pairing", "create", "--ttl", "24h", "--json")
        if p.wait() == 0:
            cred = json.loads(p.stdout.read().strip()).get("credential")
            if cred:
                pair_url = f"{clean_url}/pair#token={cred}"
                qr_code = generate_ascii_qr(pair_url)
    except Exception:
        pass

    if not pair_url:
        for _ in range(6):
            try:
                p = sandbox.exec("cat", "/tmp/t3-pairing.json")
                if p.wait() == 0:
                    cred = json.loads(p.stdout.read().strip()).get("credential")
                    if cred:
                        pair_url = f"{clean_url}/pair#token={cred}"
                        qr_code = generate_ascii_qr(pair_url)
                        break
            except Exception:
                pass
            time.sleep(0.5)

    return pair_url or clean_url, qr_code


def launch_sandbox(
    req: LaunchRequest,
    repo_root: Path | None = None,
    build_image_fn: Callable | None = None,
    load_pubkey_fn: Callable | None = None,
) -> tuple[modal.Sandbox, LaunchResponse]:
    """Provisions a Modal sandbox and executes the post-launch setup pipeline."""
    validate_launch_request(req)

    if repo_root is None:
        if (Path("/root/.secrets") / "github-orgs.env").is_file():
            repo_root = Path("/root")
        elif Path("/root/secrets/github-orgs.env").is_file():
            repo_root = Path("/root")
        else:
            repo_root = Path(__file__).resolve().parent.parent

    clean_repo = req.repo.strip().rstrip("/") if req.repo else None
    target_repo, org_name, bare_repo = None, None, None
    orgs_env_file = repo_root / ".secrets" / "github-orgs.env"
    if not orgs_env_file.is_file():
        orgs_env_file = repo_root / "secrets" / "github-orgs.env"

    if clean_repo:
        if not orgs_env_file.is_file():
            raise FileNotFoundError(
                f"Organization credentials file not found: {orgs_env_file} (expected .secrets/github-orgs.env or secrets/github-orgs.env)."
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

    if clean_repo and orgs_env_file.is_file():
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

    t3_ssh_alias = req.t3_ssh_host or sandbox_name
    if req.t3:
        encrypted_ports.append(req.t3_port)
        env["ENABLE_T3"] = "1"
        env["T3_PORT"] = str(req.t3_port)
        env["FLAGS_enforce_kernel_ipv6_support"] = "false"
        env["T3_SSH_HOST"] = t3_ssh_alias

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
    if req.react_native:
        encrypted_ports.append(req.metro_port)
        env["ENABLE_REACT_NATIVE"] = "1"
        env["METRO_PORT"] = str(req.metro_port)
        volumes.update(get_gradle_volumes())

    features = []
    if not req.no_cloudflare:
        features.append("Cloudflare Tunnel")
    if req.full_clone:
        features.append("Full Git Clone")
    if req.react_native:
        features.append("React Native")
    if req.agy:
        features.append("Antigravity")
    if req.opencode:
        features.append("OpenCode")
    if req.t3:
        features.append("T3 Code")
    if req.modal:
        features.append("Modal")
    if req.sops:
        features.append("SOPS")
    if req.herdr:
        features.append("Herdr")
    if req.pi:
        features.append("Pi")
    if browser_active:
        features.append("Browser")

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
        "volumes": volumes,
        "unencrypted_ports": [22],
        "encrypted_ports": encrypted_ports,
        "cpu": (0.125, 4.0),
        "env": env,
        "runtime": "vm" if req.vm else "gvisor",
        "memory": (128, 16384),
    }

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

    response = LaunchResponse(
        sandbox_id=sandbox.object_id,
        app_name=app_name,
        sandbox_name=sandbox_name,
        ssh_info=ssh_info,
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
) -> SnapshotResponse:
    """Flushes buffers and captures a filesystem snapshot of an active sandbox."""
    sandbox = modal.Sandbox.from_id(sandbox_id)
    sync_proc = sandbox.exec("sync")
    sync_proc.wait()

    ttl_seconds = ttl_days * 86400
    snapshot_image = sandbox.snapshot_filesystem(ttl=ttl_seconds)
    image_id = snapshot_image.object_id

    if terminate:
        sandbox.terminate()

    return SnapshotResponse(
        sandbox_id=sandbox_id,
        image_id=image_id,
        ttl_days=ttl_days,
        ttl_seconds=ttl_seconds,
        terminated=terminate,
    )
