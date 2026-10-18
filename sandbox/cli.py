"""CLI argument parsing, validation, and terminal formatting for Modal sandboxes."""

import argparse
import io

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


def print_access_info(
    sandbox: modal.Sandbox,
    app_name: str,
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
    memory_gb: int | None = None,
    agy_enabled: bool = False,
    cloudflare_enabled: bool = True,
    sops_enabled: bool = False,
):
    print("\n" + "=" * 60)
    print("🏝️  Sandbox Ready!")
    print(f"  • App:      {app_name}")
    print(f"  • Shell:    modal shell {sandbox.object_id}")
    if cloudflare_enabled:
        print(f"  • Cloudflare: https://{DEFAULT_WEB_PORT}.mahesh0.dev (port {DEFAULT_WEB_PORT})")
    if memory_gb:
        print(f"  • Memory:   {memory_gb} GB RAM + {memory_gb * 2} GB swap")
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
    if agy_enabled:
        print(f"  • Remote Control: https://antigravity.google.com (Instance: {app_name})")
    if ssh_info:
        ssh_host, ssh_port = ssh_info
        ssh_cmd = (
            f"ssh -i ~/.ssh/modal-sandbox -o StrictHostKeyChecking=no -p {ssh_port} root@{ssh_host}"
        )
        print(f"  • SSH:      {ssh_cmd}")
        print("\nVS Code / SSH Config snippet:")
        print(f"Host {app_name}")
        print(f"  HostName {ssh_host}")
        print(f"  Port {ssh_port}")
        print("  User root")
        print("  IdentityFile ~/.ssh/modal-sandbox")
        print("  StrictHostKeyChecking no")
    if t3_qr_code:
        print("\n📱 Scan with T3 Code Mobile App (iOS / Android):")
        for line in t3_qr_code.splitlines():
            print(f"  {line}")
    print("=" * 60 + "\n")


class SnapshotTTLAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)
        setattr(namespace, "_snapshot_ttl_specified", True)


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launch a repository in a Modal Sandbox (Standard Container or Linux VM) with SSH & Cloudflare Ingress"
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
        help="Explicit Modal application name (mandatory when launching without --secret).",
    )

    parser.add_argument(
        "-b",
        "--github-branch",
        default="main",
        help="Git branch to checkout. Only branches are supported (not tags or commits). Default: main",
    )
    parser.add_argument(
        "-s",
        "--secret",
        dest="secret",
        default=None,
        help="Repository secret name under secrets/<secret-name>/fetch.env (optional; when omitted, launches a Standalone Sandbox without repository fetch).",
    )

    parser.add_argument(
        "--testing",
        "--test",
        dest="testing",
        action="store_true",
        help="Resolve repository secrets from canonical Test Organization (secrets_org/software-factory-09-test/token) instead of secrets/<secret-name>/fetch.env.",
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
        help="RAM to allocate in GB (1 -> 1 GB, 2 -> 2 GB, ...). Swap is 2x RAM. Only valid with --vm (default with --vm: 1).",
    )
    parser.add_argument(
        "--no-cloudflare",
        action="store_true",
        help="Disable the default Cloudflare Tunnel (3000.mahesh0.dev) for this sandbox.",
    )
    parser.add_argument(
        "--sops",
        action="store_true",
        help="Retain SOPS age private key and credentials in ~/.config/sops for interactive debugging.",
    )
    return parser


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.snapshot:
        if args.from_snapshot:
            parser.error("--snapshot and --from-snapshot cannot be used together.")
        if args.secret:
            parser.error("--snapshot cannot be used with --secret.")
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
        ):
            parser.error("--snapshot cannot be used with launch configuration arguments.")
    else:
        if args.terminate:
            parser.error("--terminate can only be used with --snapshot.")
        if getattr(args, "_snapshot_ttl_specified", False):
            parser.error("--snapshot-ttl can only be used with --snapshot.")
        if args.from_snapshot and not args.secret and not args.name:
            parser.error("--name is required when launching from a snapshot without --secret.")
        if not args.secret and not args.name:
            parser.error("--name is required when launching without --secret.")
        if not args.secret and args.github_branch != "main":
            parser.error("--github-branch cannot be used without -s/--secret.")
        if not args.secret and args.testing:
            parser.error("--testing cannot be used without -s/--secret.")


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
