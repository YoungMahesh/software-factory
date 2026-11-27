"""Remote infrastructure deployment module for Resource Plane on a Linux VPS.

Automates SSH connectivity validation, remote Docker environment verification,
repository directory synchronization, and production deployment execution
using system ssh and tar via subprocess (zero third-party dependencies).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from sandbox.config import parse_env_file, resolve_factory_root
from sandbox.source_transfer import stream_source_archive


DEFAULT_REMOTE_DIR = "/opt/resource-plane"
DEFAULT_SSH_PORT = 22
DEFAULT_SSH_USER = "root"


@dataclass
class VpsSshConfig:
    """Configuration required to connect and deploy to a target VPS."""
    host: str
    key_path: Path
    user: str = DEFAULT_SSH_USER
    port: int = DEFAULT_SSH_PORT
    remote_dir: str = DEFAULT_REMOTE_DIR


def _materialize_ssh_private_key(private_key: str) -> Path:
    """Writes inline SSH private key material to a stable 0600 temp file."""
    normalized = private_key.replace("\r\n", "\n").rstrip() + "\n"
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    key_path = Path(tempfile.gettempdir()) / f"software-factory-vps-{digest}"
    if not key_path.is_file() or key_path.read_text(encoding="utf-8") != normalized:
        key_path.write_text(normalized, encoding="utf-8")
    key_path.chmod(0o600)
    return key_path


def resolve_vps_ssh_config(
    host: str | None = None,
    user: str | None = None,
    port: int | None = None,
    key_path: str | Path | None = None,
    remote_dir: str | None = None,
    *,
    private_key: str | None = None,
    dotenv: dict[str, str] | None = None,
) -> VpsSshConfig:
    """Resolves VPS SSH connection configuration from arguments or environment."""
    file_env = dotenv or {}

    resolved_host = (
        host
        or os.environ.get("RESOURCE_PLANE_SSH_HOST")
        or file_env.get("RESOURCE_PLANE_SSH_HOST")
    )
    if not resolved_host or not resolved_host.strip():
        raise ValueError(
            "Missing VPS SSH host. Set RESOURCE_PLANE_SSH_HOST in .env."
        )

    resolved_user = (
        user
        or os.environ.get("RESOURCE_PLANE_SSH_USER")
        or file_env.get("RESOURCE_PLANE_SSH_USER")
        or DEFAULT_SSH_USER
    )
    raw_port = (
        port
        or os.environ.get("RESOURCE_PLANE_SSH_PORT")
        or file_env.get("RESOURCE_PLANE_SSH_PORT")
        or DEFAULT_SSH_PORT
    )
    resolved_port = int(raw_port)
    raw_private_key = (
        private_key
        or os.environ.get("RESOURCE_PLANE_SSH_PRIVATE_KEY")
        or file_env.get("RESOURCE_PLANE_SSH_PRIVATE_KEY")
    )
    raw_key = (
        key_path
        or os.environ.get("RESOURCE_PLANE_SSH_KEY")
        or file_env.get("RESOURCE_PLANE_SSH_KEY")
    )

    resolved_key: Path | None = None
    if raw_key and str(raw_key).strip():
        key_p = Path(raw_key).expanduser()
        candidate = (resolve_factory_root() / key_p).resolve() if not key_p.is_absolute() else key_p.resolve()
        if candidate.is_file():
            resolved_key = candidate
        elif not raw_private_key or not raw_private_key.strip():
            raise FileNotFoundError(f"SSH private key file not found: {candidate}")

    if resolved_key is None:
        if raw_private_key and raw_private_key.strip():
            resolved_key = _materialize_ssh_private_key(raw_private_key)
        else:
            raise ValueError(
                "Missing required SSH key. Set RESOURCE_PLANE_SSH_KEY in .env."
            )

    try:
        key_bytes = resolved_key.read_bytes()
        if b"-----BEGIN " in key_bytes and key_bytes.rstrip(b" \t\r\n").endswith(b"PRIVATE KEY-----"):
            if not key_bytes.endswith(b"\n"):
                resolved_key.write_bytes(key_bytes.rstrip(b"\r") + b"\n")
                print(f"🔑 Normalized trailing newline on SSH key: {resolved_key}", file=sys.stderr)
        current_mode = resolved_key.stat().st_mode & 0o777
        if current_mode != 0o600:
            resolved_key.chmod(0o600)
            print(f"🔒 Normalized permissions on SSH key to 0600: {resolved_key}", file=sys.stderr)
    except OSError:
        pass

    resolved_remote_dir = remote_dir or DEFAULT_REMOTE_DIR

    return VpsSshConfig(
        host=resolved_host.strip(),
        user=resolved_user.strip(),
        port=resolved_port,
        key_path=resolved_key,
        remote_dir=resolved_remote_dir.strip(),
    )


def build_ssh_cmd(config: VpsSshConfig, remote_cmd: str | None = None) -> list[str]:
    """Constructs the base SSH command list honoring port, key, and user options."""
    cmd = [
        "ssh",
        "-p",
        str(config.port),
        "-i",
        str(config.key_path),
        f"{config.user}@{config.host}",
    ]
    if remote_cmd:
        cmd.append(remote_cmd)
    return cmd


def check_ssh_connection(config: VpsSshConfig, timeout: int = 15) -> bool:
    """Verifies basic SSH connectivity to the remote host."""
    cmd = build_ssh_cmd(config, "exit 0")
    try:
        res = subprocess.run(cmd, timeout=timeout, capture_output=True, text=True, check=False)
        return res.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def check_remote_docker(config: VpsSshConfig, timeout: int = 20) -> tuple[bool, str]:
    """Verifies that Docker Engine and Docker Compose V2 are available on the VPS."""
    check_script = (
        "if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1 && "
        "docker compose version >/dev/null 2>&1; then echo ok; else echo missing; fi"
    )
    cmd = build_ssh_cmd(config, check_script)
    try:
        res = subprocess.run(cmd, timeout=timeout, capture_output=True, text=True, check=False)
        if res.returncode == 0 and "ok" in res.stdout:
            return True, "Docker Engine and Docker Compose V2 detected."
        return False, (
            "Docker Engine or Docker Compose V2 is missing or non-functional on remote VPS. "
            "Please ensure Docker is installed and the SSH user has permission to /var/run/docker.sock."
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"Failed to probe remote Docker: {exc}"


def find_resource_plane_source_dir(start_path: Path | None = None) -> Path:
    """Discovers the local resource-plane directory relative to current module or repo root."""
    current = (start_path or Path(__file__)).resolve()
    candidates = [
        current.parent / "resource-plane",
        current.parent.parent / "resource-plane",
        current.parent.parent.parent / "resource-plane",
        Path.cwd() / "resource-plane",
    ]
    for cand in candidates:
        if cand.is_dir() and (cand / "deploy.sh").is_file():
            return cand
    raise FileNotFoundError(
        "Could not locate local 'resource-plane' directory containing deploy.sh. "
        "Ensure you are running from within the software-factory monorepo."
    )


def sync_resource_plane_to_vps(
    config: VpsSshConfig,
    source_dir: Path | None = None,
    timeout: int = 180,
) -> bool:
    """Synchronizes the local resource-plane directory to the remote VPS using tar over SSH."""
    src = source_dir or find_resource_plane_source_dir()
    parent_dir = src.parent
    folder_name = src.name

    tar_create_cmd = [
        "tar",
        "-czf",
        "-",
        "--exclude=.git",
        "--exclude=node_modules",
        "--exclude=.data",
        "--exclude=.env",
        "--exclude=.next",
        "--exclude=caddy",
        "-C",
        str(parent_dir),
        folder_name,
    ]

    remote_extract_script = f"mkdir -p '{config.remote_dir}' && tar -xzf - -C '{config.remote_dir}' --strip-components=1"
    ssh_extract_cmd = build_ssh_cmd(config, remote_extract_script)

    try:
        stream_source_archive(tar_create_cmd, ssh_extract_cmd, timeout=timeout)
        return True
    except (RuntimeError, OSError) as exc:
        print(f"❌ File synchronization to VPS failed: {exc}", file=sys.stderr)
        return False


def execute_remote_deploy(
    config: VpsSshConfig,
    stream: bool = True,
    timeout: int = 600,
) -> tuple[int, str]:
    """Executes deploy.sh remotely on the VPS inside the destination directory."""
    remote_script = (
        f"cd '{config.remote_dir}' && "
        "chmod +x deploy.sh scripts/*.sh 2>/dev/null || true; "
        "./deploy.sh"
    )
    cmd = build_ssh_cmd(config, remote_script)

    if stream:
        res = subprocess.run(cmd, check=False)
        return res.returncode, ""

    res = subprocess.run(cmd, timeout=timeout, capture_output=True, text=True, check=False)
    return res.returncode, res.stdout + ("\n" + res.stderr if res.stderr else "")


def fetch_remote_admin_token(config: VpsSshConfig, timeout: int = 15) -> str | None:
    """Retrieves ADMIN_TOKEN directly from the remote resource-plane .env over SSH."""
    remote_cmd = (
        f"cat '{config.remote_dir}/.env' 2>/dev/null | "
        "grep -E '^[[:space:]]*ADMIN_TOKEN=' | head -n1 | cut -d= -f2- | tr -d '\"'\'' \r\n'"
    )
    cmd = build_ssh_cmd(config, remote_cmd)
    try:
        res = subprocess.run(cmd, timeout=timeout, capture_output=True, text=True, check=False)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def sync_env_keys(
    env_file_path: Path,
    keys_to_set: dict[str, str],
) -> tuple[bool, list[str]]:
    """Synchronizes environment key-value pairs to local .env idempotently without clobbering."""
    if not keys_to_set:
        return False, []

    if not env_file_path.exists():
        env_file_path.parent.mkdir(parents=True, exist_ok=True)
        content = "\n".join(f'{k}="{v}"' for k, v in keys_to_set.items()) + "\n"
        env_file_path.write_text(content, encoding="utf-8")
        return True, list(keys_to_set.keys())

    content = env_file_path.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    existing_vars = parse_env_file(env_file_path)

    updated_keys: list[str] = []
    preserved_keys: list[str] = []

    for key, value in keys_to_set.items():
        existing_val = existing_vars.get(key, "").strip()
        if existing_val:
            preserved_keys.append(key)
            continue

        pattern = re.compile(rf"^\s*(export\s+)?{re.escape(key)}\s*=.*$")
        new_line = f'{key}="{value}"\n'
        replaced = False
        new_lines: list[str] = []

        for line in lines:
            if pattern.match(line):
                new_lines.append(new_line)
                replaced = True
            else:
                new_lines.append(line)

        if not replaced:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines[-1] += "\n"
            new_lines.append(new_line)

        lines = new_lines
        updated_keys.append(key)

    if updated_keys:
        env_file_path.write_text("".join(lines), encoding="utf-8")
        return True, updated_keys

    return False, preserved_keys


def sync_local_env_credentials(
    env_file_path: Path,
    domain: str,
    admin_token: str | None = None,
) -> tuple[bool, list[str]]:
    """Synchronizes domain and admin token to local .env idempotently without clobbering."""
    keys_to_set: dict[str, str] = {"RESOURCE_PLANE_DOMAIN": domain}
    if admin_token:
        keys_to_set["RESOURCE_PLANE_ADMIN_TOKEN"] = admin_token
    return sync_env_keys(env_file_path, keys_to_set)


def deploy_resource_plane(
    config: VpsSshConfig | None = None,
    stream: bool = True,
    sync_env: bool = True,
) -> int:
    """Coordinates full automated deployment of Resource Plane to the target VPS."""
    cfg = config or resolve_vps_ssh_config()

    print(f"\n🚀 Deploying Resource Plane to VPS {cfg.user}@{cfg.host}:{cfg.port}...")
    print(f"   Remote directory: {cfg.remote_dir}")

    # 1. Connectivity check
    print("==> Checking SSH connectivity...")
    if not check_ssh_connection(cfg):
        print(
            f"❌ Cannot connect via SSH to {cfg.user}@{cfg.host}:{cfg.port}. "
            "Please check network reachability, firewall rules, and SSH keys.",
            file=sys.stderr,
        )
        return 1
    print("   ✓ SSH connection established.")

    # 2. Remote Docker check
    print("==> Verifying remote Docker environment...")
    docker_ok, docker_msg = check_remote_docker(cfg)
    if not docker_ok:
        print(f"❌ {docker_msg}", file=sys.stderr)
        return 1
    print(f"   ✓ {docker_msg}")

    # 3. Synchronize files
    print("==> Synchronizing resource-plane files to remote VPS...")
    if not sync_resource_plane_to_vps(cfg):
        return 1
    print("   ✓ Files synchronized.")

    # 4. Run remote deploy.sh
    print("==> Executing remote deploy.sh (starting containers & migrations)...")
    code, output = execute_remote_deploy(cfg, stream=stream)
    if code != 0:
        print(f"\n❌ Remote deployment failed with exit code {code}.", file=sys.stderr)
        if output:
            print(output, file=sys.stderr)
        return code

    print("\n✅ Resource Plane successfully deployed to VPS!")
    print(f"   Dashboard / Web UI: http://{cfg.host}:3000")
    print(f"   PostgreSQL Port:   54320 (or configured host port)")
    print(f"   SeaweedFS S3 Port: 8333")

    if sync_env:
        admin_token = fetch_remote_admin_token(cfg)
        root_env = resolve_factory_root() / ".env"
        updated, modified_keys = sync_local_env_credentials(
            root_env,
            domain=cfg.host,
            admin_token=admin_token,
        )
        if updated:
            print(f"\n   ✓ Synchronized {', '.join(modified_keys)} to {root_env.name}")
        elif modified_keys:
            print(f"\n   ℹ Existing {', '.join(modified_keys)} preserved in {root_env.name}")
    else:
        print("\nNext step: ensure RESOURCE_PLANE_DOMAIN and RESOURCE_PLANE_ADMIN_TOKEN are configured in .env\n")

    return 0


def create_parser() -> argparse.ArgumentParser:
    """Builds the argument parser for infra deployment."""
    parser = argparse.ArgumentParser(
        prog="modal-sandbox infra deploy",
        description="Deploy Resource Plane (PostgreSQL & S3 control plane) to /opt/resource-plane via SSH.",
    )
    parser.add_argument("--check-only", action="store_true", help="Only verify SSH and Docker connectivity without deploying.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for infra deployment."""
    parser = create_parser()
    args = parser.parse_args(argv)

    try:
        cfg = resolve_vps_ssh_config(
            dotenv=parse_env_file(resolve_factory_root() / ".env"),
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1

    if args.check_only:
        print(f"Probing {cfg.user}@{cfg.host}:{cfg.port}...")
        if not check_ssh_connection(cfg):
            print("❌ SSH connection failed.", file=sys.stderr)
            return 1
        ok, msg = check_remote_docker(cfg)
        print("✓ " if ok else "❌ ", msg)
        return 0 if ok else 1

    return deploy_resource_plane(cfg, stream=True, sync_env=True)


if __name__ == "__main__":
    sys.exit(main())
