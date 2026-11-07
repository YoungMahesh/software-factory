"""Terminal formatting, QR code generation, and SSH configuration helpers."""

import io
from pathlib import Path
import sys

import modal

from .config import DEFAULT_WEB_PORT


def generate_ascii_qr(data: str) -> str | None:
    """Generates an inverted unicode ASCII QR code string for terminal display."""
    try:
        import qrcode

        qr = qrcode.QRCode(border=1)
        qr.add_data(data)
        buf = io.StringIO()
        qr.print_ascii(out=buf, invert=True)
        return buf.getvalue().rstrip()
    except Exception:
        return None


def generate_ssh_config_snippet(
    instance_name: str,
    ssh_host: str,
    ssh_port: int,
) -> str:
    """Generates the SSH client config block for the sandbox instance."""
    return (
        f"Host {instance_name}\n"
        f"  HostName {ssh_host}\n"
        f"  Port {ssh_port}\n"
        f"  User root\n"
        f"  IdentityFile ~/.ssh/modal-sandbox\n"
        f"  StrictHostKeyChecking no\n"
        f"  UserKnownHostsFile /dev/null\n"
    )


def append_ssh_config(
    instance_name: str,
    ssh_host: str,
    ssh_port: int,
    config_path: Path | None = None,
) -> bool:
    """Appends SSH connection details to ~/.ssh/config.

    Returns True if successfully appended, False otherwise.
    Never raises an exception; logs warning to stderr on failure.
    """
    if config_path is None:
        config_path = Path("~/.ssh/config").expanduser()

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        snippet = generate_ssh_config_snippet(instance_name, ssh_host, ssh_port)

        prefix = ""
        if config_path.is_file() and config_path.stat().st_size > 0:
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()
                if not content.endswith("\n\n"):
                    if content.endswith("\n"):
                        prefix = "\n"
                    else:
                        prefix = "\n\n"

        with open(config_path, "a", encoding="utf-8") as f:
            f.write(prefix + snippet)
        return True
    except Exception as exc:
        print(
            f"⚠️  Warning: Failed to append SSH connection details to {config_path}: {exc}",
            file=sys.stderr,
        )
        return False


def print_access_info(
    sandbox: modal.Sandbox | None = None,
    app_name: str = "",
    sandbox_name: str | None = None,
    ssh_info: tuple[str, int] | None = None,
    opencode_url: str | None = None,
    opencode_port: int | None = None,
    opencode_password: str | None = None,
    metro_url: str | None = None,
    metro_port: int | None = None,
    t3_url: str | None = None,
    t3_port: int | None = None,
    t3_pair_url: str | None = None,
    t3_qr_code: str | None = None,
    t3_ssh_host: str | None = None,
    t3_persist: bool = False,
    t3_usage_volume: str | None = None,
    memory_gb: int | None = None,
    agy_enabled: bool = False,
    cloudflare_enabled: bool = True,
    sops_enabled: bool = False,
    is_vm: bool = False,
    sandbox_id: str | None = None,
):
    print("\n" + "=" * 60)
    print("🏝️  Sandbox Ready!")
    print(f"  • App:      {app_name}")
    if sandbox_name:
        print(f"  • Sandbox:  {sandbox_name}")
    sb_id = sandbox_id or (sandbox.object_id if sandbox else "unknown")
    print(f"  • Shell:    modal shell {sb_id}")
    if cloudflare_enabled:
        print(f"  • Cloudflare: https://{DEFAULT_WEB_PORT}.mahesh0.dev (port {DEFAULT_WEB_PORT})")
    if memory_gb:
        print(f"  • Memory:   Burstable (128 MiB - 16 GiB) + {memory_gb * 2} GB swap")
    elif is_vm:
        print("  • Memory:   Burstable (128 MiB - 16 GiB) + 2 GB swap")
    if metro_url:
        print(f"  • Metro:    {metro_url} (port {metro_port})")
    if sops_enabled:
        print("  • SOPS:     Configured (~/.config/sops/age/keys.txt)")
    if opencode_url:
        print(f"  • OpenCode: {opencode_url} (port {opencode_port}, User: opencode)")
        if opencode_password:
            print(f"  • Password: {opencode_password}")
            print(
                f"  • Attach:   OPENCODE_SERVER_PASSWORD={opencode_password} "
                f"opencode --server {opencode_url}"
            )
    if t3_pair_url:
        print(f"  • T3 Code:  {t3_pair_url}")
    elif t3_url:
        print(f"  • T3 Code:  {t3_url} (port {t3_port})")
        print(f"  • Web UI:   {t3_url}")
    if t3_persist and (t3_pair_url or t3_url):
        print(f"  • T3 Storage: Persistent volume ({t3_usage_volume or 't3code-usage-v1'})")
    instance_name = t3_ssh_host or sandbox_name or app_name
    if agy_enabled:
        print(f"  • Remote Control: https://antigravity.google.com (Instance: {instance_name})")
    if ssh_info:
        ssh_host, ssh_port = ssh_info
        ssh_cmd = (
            f"ssh -i ~/.ssh/modal-sandbox -o StrictHostKeyChecking=no -p {ssh_port} root@{ssh_host}"
        )
        print(f"  • SSH:      {ssh_cmd}")
        print("\nVS Code / SSH Config snippet:")
        print(generate_ssh_config_snippet(instance_name, ssh_host, ssh_port).rstrip("\n"))
    if t3_qr_code:
        print("\nScan with T3 Code Mobile App (iOS / Android):")
        for line in t3_qr_code.splitlines():
            print(f"  {line}")
    print("=" * 60 + "\n")


def print_snapshot_info(
    snapshot_id: str,
    image_id: str,
    name: str,
    ttl_days: int,
    expires_at: float,
    sandbox_id: str,
    profile: str | None = None,
) -> None:
    """Prints friendly CLI summary for captured or inspected snapshots."""
    import datetime

    exp_date = datetime.datetime.fromtimestamp(expires_at, datetime.timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )
    print("\n" + "=" * 60)
    print("📸  Snapshot Summary")
    print(f"  • Name:        {name}")
    print(f"  • Snapshot ID: {snapshot_id}")
    print(f"  • Image ID:    {image_id}")
    print(f"  • Source SB:   {sandbox_id}")
    if profile:
        print(f"  • Profile:     {profile}")
    print(f"  • Retention:   {ttl_days} days (Expires: {exp_date})")
    print(f"  • Resume:      python3 sandbox/main.py --from-snapshot {image_id} --name resumed-sandbox")
    print("=" * 60 + "\n")
