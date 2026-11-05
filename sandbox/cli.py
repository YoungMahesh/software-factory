"""CLI argument parsing, validation, and terminal formatting for Modal sandboxes."""

import argparse
import io
import os
from pathlib import Path
import sys

import modal

from .config import (
    DEFAULT_METRO_PORT,
    DEFAULT_OPENCODE_PORT,
    DEFAULT_T3_PORT,
    DEFAULT_WEB_PORT,
)


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
        print("\n📱 Scan with T3 Code Mobile App (iOS / Android):")
        for line in t3_qr_code.splitlines():
            print(f"  {line}")
    print("=" * 60 + "\n")


def print_snapshot_info(
    sandbox_id: str,
    image_id: str,
    ttl_days: int = 30,
    ttl_seconds: int | None = None,
    is_vm: bool = False,
    terminate: bool = False,
) -> None:
    """Formats and prints snapshot capture confirmation."""
    ttl_secs = ttl_seconds if ttl_seconds is not None else ttl_days * 86400
    vm_flag = " --vm" if is_vm else ""
    print("\n" + "=" * 60)
    print("📸  Filesystem Snapshot Captured!")
    print(f"  • Sandbox ID:  {sandbox_id}")
    print(f"  • Image ID:    {image_id}")
    print(f"  • Retention:   {ttl_days} days ({ttl_secs}s)")
    print(f"  • Resume:      python3 sandbox/main.py --from-snapshot {image_id} --name resumed-sandbox{vm_flag}")
    print("=" * 60 + "\n")

    if terminate:
        print(f"🧹 Terminating sandbox {sandbox_id}...")
        print(f"✅ Sandbox {sandbox_id} terminated.")
    else:
        print(f"ℹ️  Sandbox {sandbox_id} remains running (non-destructive snapshot).")


class SnapshotTTLAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)
        setattr(namespace, "_snapshot_ttl_specified", True)


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launch a repository in a Modal Sandbox (Standard Container or Linux VM) with SSH & Cloudflare Ingress"
    )
    # Remote execution flags
    parser.add_argument(
        "--remote",
        action="store_true",
        help="Delegate execution to the hosted Modal control plane function.",
    )
    parser.add_argument(
        "--endpoint-url",
        default=None,
        metavar="URL",
        help="Override endpoint URL for --remote (defaults to MODAL_SANDBOX_ENDPOINT_URL).",
    )

    # Filesystem Snapshot capture flags
    parser.add_argument(
        "--snapshot",
        metavar="SANDBOX_ID",
        default=None,
        help="Capture a root filesystem snapshot of an active sandbox by ID.",
    )
    parser.add_argument(
        "--snapshot-ttl",
        type=int,
        default=30,
        action=SnapshotTTLAction,
        metavar="DAYS",
        help="Time-to-live in days for the captured snapshot image (default: 30 days).",
    )
    parser.add_argument(
        "--terminate",
        action="store_true",
        help="Terminate the target sandbox immediately after snapshot capture.",
    )

    # Filesystem Snapshot restoration flags
    parser.add_argument(
        "--from-snapshot",
        metavar="IMAGE_ID",
        default=None,
        help="Launch a sandbox directly from a filesystem snapshot image ID.",
    )
    parser.add_argument(
        "--name",
        default=None,
        metavar="APP_NAME",
        help="Explicit Modal application name for standalone sandboxes (mandatory when launching without -r/--repo; cannot be used with -r/--repo).",
    )

    parser.add_argument(
        "-b",
        "--github-branch",
        default="main",
        help="Git branch to checkout. Only branches are supported (not tags or commits). Default: main",
    )
    parser.add_argument(
        "--full-clone",
        action="store_true",
        help="Clone complete Git commit history instead of default shallow clone (--depth 50).",
    )
    parser.add_argument(
        "-r",
        "--repo",
        dest="repo",
        default=None,
        help="Target GitHub repository name (e.g. sFactory0/software-factory or shorthand software-factory). When omitted, launches a Standalone Sandbox without repository fetch.",
    )

    parser.add_argument(
        "--testing",
        "--test",
        dest="testing",
        action="store_true",
        help="Target repository under canonical organization sFactory0 using test- prefix (e.g. sFactory0/test-<repo>).",
    )
    parser.add_argument(
        "--opencode",
        action="store_true",
        help="Also run an OpenCode server in the sandbox and expose its WebUI over public HTTPS URL.",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Also pre-bake a headless Google Chrome shared by the Playwright and Chrome DevTools MCP servers. Implied by --opencode and --agy.",
    )
    parser.add_argument(
        "--agy",
        action="store_true",
        help="Also set up antigravity-cli and launch the background Antigravity Remote Control daemon (mounts shared settings, keybindings & onboarding and automatically enables SOPS secret decryption).",
    )
    parser.add_argument(
        "--opencode-port",
        type=int,
        default=DEFAULT_OPENCODE_PORT,
        help=f"Port for the OpenCode server, only used with --opencode (default: {DEFAULT_OPENCODE_PORT})",
    )
    parser.add_argument(
        "--t3",
        "--t3code",
        action="store_true",
        dest="t3",
        help="Also run a T3 Code server in the sandbox and expose its WebUI over public HTTPS URL.",
    )
    parser.add_argument(
        "--t3-port",
        type=int,
        default=DEFAULT_T3_PORT,
        help=f"Port for the T3 Code server, only used with --t3 (default: {DEFAULT_T3_PORT})",
    )
    parser.add_argument(
        "--t3-ssh-host",
        default=None,
        help="SSH host alias to use in T3 Code for 'Open in VS Code' links (defaults to sandbox instance name).",
    )
    parser.add_argument(
        "--react-native",
        action="store_true",
        help="Also configure Android SDK, NDK, OpenJDK 17, Gradle cache volumes, and Metro bundler port forwarding for React Native.",
    )
    parser.add_argument(
        "--modal",
        action="store_true",
        help="Also configure Python 3, virtual environment, Modal SDK, and decrypt Modal client credentials.",
    )
    parser.add_argument(
        "--metro-port",
        type=int,
        default=DEFAULT_METRO_PORT,
        help=f"Port for the React Native Metro bundler, only used with --react-native (default: {DEFAULT_METRO_PORT})",
    )
    parser.add_argument(
        "--vm",
        action="store_true",
        help="Launch as a full Linux VM Sandbox (virtualization, Docker daemon, custom kernel privileges, swapfile allocation).",
    )
    parser.add_argument(
        "--memory",
        type=int,
        default=None,
        metavar="GB",
        help="(Deprecated) Formerly set static VM RAM; VM sandboxes now use burstable RAM (128, 16384) MiB. If provided with --vm, sizes swapfile to 2 * N GB.",
    )
    parser.add_argument(
        "--no-cloudflare",
        action="store_true",
        help="Disable the default Cloudflare Tunnel (3000.mahesh0.dev) for this sandbox.",
    )
    parser.add_argument(
        "--no-ssh-config",
        action="store_true",
        help="Do not automatically append SSH connection details to ~/.ssh/config.",
    )
    parser.add_argument(
        "--sops",
        action="store_true",
        help="Retain SOPS age private key and credentials in ~/.config/sops for interactive debugging.",
    )
    parser.add_argument(
        "--herdr",
        action="store_true",
        help="Also install Herdr agent multiplexer (https://herdr.dev) into /usr/local/bin in the sandbox.",
    )
    parser.add_argument(
        "--pi",
        action="store_true",
        help="Also install Pi coding agent CLI (https://pi.dev) and configure OpenCode Go with DeepSeek V4.1 Flash in the sandbox.",
    )
    return parser


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.endpoint_url and not args.remote:
        parser.error("--endpoint-url can only be used with --remote.")

    if args.snapshot:
        if args.from_snapshot:
            parser.error("--snapshot and --from-snapshot cannot be used together.")
        if args.repo:
            parser.error("--snapshot cannot be used with -r/--repo.")
        if args.name:
            parser.error("--snapshot cannot be used with --name.")
        if args.testing:
            parser.error("--snapshot cannot be used with --testing.")
        if args.vm:
            parser.error("--snapshot cannot be used with --vm.")
        if args.memory is not None:
            parser.error("--snapshot cannot be used with --memory.")
        if args.no_cloudflare:
            parser.error("--snapshot cannot be used with --no-cloudflare.")
        if args.github_branch != "main":
            parser.error("--snapshot cannot be used with --github-branch.")
        if args.snapshot_ttl <= 0:
            parser.error("--snapshot-ttl must be a positive integer.")
        if (
            args.opencode
            or args.react_native
            or args.modal
            or args.sops
            or args.browser
            or args.agy
            or args.t3
            or args.t3_ssh_host
            or args.herdr
            or args.pi
            or args.full_clone
            or getattr(args, "no_ssh_config", False)
        ):
            parser.error("--snapshot cannot be used with launch configuration arguments.")
    else:
        if args.terminate:
            parser.error("--terminate can only be used with --snapshot.")
        if getattr(args, "_snapshot_ttl_specified", False):
            parser.error("--snapshot-ttl can only be used with --snapshot.")
        if args.repo and args.name:
            parser.error(
                "--name cannot be used with -r/--repo: --name is strictly for standalone launches without -r/--repo."
            )
        if args.from_snapshot and not args.repo and not args.name:
            parser.error("--name is required when launching from a snapshot without -r/--repo.")
        if not args.repo and not args.name:
            parser.error("--name is required when launching without -r/--repo.")
        if not args.repo and args.github_branch != "main":
            parser.error("--github-branch cannot be used without -r/--repo.")
        if not args.repo and args.testing:
            parser.error("--testing cannot be used without -r/--repo.")
        if args.from_snapshot and args.full_clone:
            parser.error("--full-clone cannot be used with --from-snapshot.")
        if not args.repo and args.full_clone:
            parser.error("--full-clone cannot be used without -r/--repo.")
        if args.t3_ssh_host and not args.t3:
            parser.error("--t3-ssh-host can only be used with --t3.")


def capture_snapshot(
    sandbox_id: str,
    ttl_days: int = 30,
    terminate: bool = False,
) -> str:
    print(f"🔄 Flushing filesystem buffers inside sandbox {sandbox_id}...")
    sandbox = modal.Sandbox.from_id(sandbox_id)
    sync_proc = sandbox.exec("sync")
    sync_proc.wait()

    is_vm = False
    try:
        vm_proc = sandbox.exec("sh", "-c", "[ -S /var/run/docker.sock ] || [ -f /swapfile ]")
        if vm_proc.wait() == 0:
            is_vm = True
    except Exception:
        is_vm = False

    if is_vm:
        print(
            "⚠️  Notice: VM Sandbox detected. Mounted volumes and Docker daemon storage "
            "(/var/lib/docker) are ephemeral and not persisted in root filesystem snapshots."
        )

    ttl_seconds = ttl_days * 86400
    print(f"📸 Capturing filesystem snapshot (retention: {ttl_days} days)...")
    snapshot_image = sandbox.snapshot_filesystem(ttl=ttl_seconds)
    image_id = snapshot_image.object_id

    vm_flag = " --vm" if is_vm else ""
    print("\n" + "=" * 60)
    print("📸  Filesystem Snapshot Captured!")
    print(f"  • Sandbox ID:  {sandbox_id}")
    print(f"  • Image ID:    {image_id}")
    print(f"  • Retention:   {ttl_days} days ({ttl_seconds}s)")
    print(f"  • Resume:      python3 sandbox/main.py --from-snapshot {image_id} --name resumed-sandbox{vm_flag}")
    print("=" * 60 + "\n")

    if terminate:
        print(f"🧹 Terminating sandbox {sandbox_id}...")
        sandbox.terminate()
        print(f"✅ Sandbox {sandbox_id} terminated.")
    else:
        print(f"ℹ️  Sandbox {sandbox_id} remains running (non-destructive snapshot).")

    return image_id
