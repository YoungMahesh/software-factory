import argparse
import io
import json
from pathlib import Path
import secrets
import sys
import time
import uuid

import modal

# Ensure repository root is on sys.path for shared imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.image import (
    REMOTE_FETCH_SECRET,
    REMOTE_ORG_SECRETS_DIR,
    REMOTE_REPO_SECRETS_DIR,
    REMOTE_STARTUP_SCRIPT,
    SHARED_SECRET_NAME,
    browser_enabled,
    build_sandbox_image,
    get_gradle_volumes,
    load_ssh_pub_key,
)

DEFAULT_TEST_ORG = "software-factory-09-test"

# Modal's default timeout for Sandbox.create is 300s (5 minutes) if omitted; max allowed is 24 hours.
TIMEOUT_SECS = 22 * 60 * 60  # 22 hours
IDLE_TIMEOUT_SECS = 4 * 60 * 60  # 4 hours
DEFAULT_WEB_PORT = 3000
DEFAULT_OPENCODE_PORT = 4096
DEFAULT_METRO_PORT = 8081
DEFAULT_T3_PORT = 3775


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
        help="Explicit Modal application name (mandatory when launching with --from-snapshot without --secret).",
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
        help="Repository secret name under secrets/<secret-name>/fetch.env",
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
        if not args.from_snapshot and not args.secret:
            parser.error("the following arguments are required: -s/--secret")


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


def run_sandbox_launch(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser | None = None,
    repo_root: Path | None = None,
):
    if parser is None:
        parser = create_parser()

    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent

    # Normalize secret name and detect testing mode
    clean_secret = args.secret.strip().rstrip("/") if args.secret else None
    is_testing = args.testing
    target_repo = None
    is_org = False
    secrets_dir = None

    if clean_secret:
        if clean_secret.startswith("secrets_testing/"):
            clean_secret = clean_secret[len("secrets_testing/"):]
            is_testing = True
        elif clean_secret.startswith("secrets_org/"):
            clean_secret = clean_secret[len("secrets_org/"):]
            is_testing = True
        elif clean_secret.startswith("secrets/"):
            clean_secret = clean_secret[len("secrets/"):]
        elif clean_secret.startswith(f"{DEFAULT_TEST_ORG}/") or clean_secret == DEFAULT_TEST_ORG:
            is_testing = True

        if is_testing:
            if "/" in clean_secret:
                org_name = clean_secret.split("/", 1)[0]
                target_repo = clean_secret
            else:
                if (repo_root / "secrets_org" / clean_secret).is_dir():
                    org_name = clean_secret
                else:
                    org_name = DEFAULT_TEST_ORG
                    target_repo = f"{DEFAULT_TEST_ORG}/{clean_secret}"

            secrets_dir = repo_root / "secrets_org" / org_name
            token_file = secrets_dir / "token"
            if not token_file.is_file():
                parser.error(
                    f"Organization token secret not found: {token_file} (expected secrets_org/{org_name}/token)."
                )
            is_org = True
        else:
            secrets_dir = repo_root / "secrets" / clean_secret
            secret_file = secrets_dir / "fetch.env"
            if not secret_file.is_file():
                parser.error(
                    f"Repository secret file not found: {secret_file} (expected secrets/{clean_secret}/fetch.env)."
                )

    if args.memory is not None:
        if not args.vm:
            parser.error("--memory can only be used with --vm.")
        if args.memory < 1:
            parser.error("--memory must be a positive integer number of GB.")

    if args.opencode and args.opencode_port == DEFAULT_WEB_PORT:
        parser.error(
            f"--opencode-port cannot be {DEFAULT_WEB_PORT}: port {DEFAULT_WEB_PORT} is reserved for web servers and Cloudflare Tunnel."
        )

    if args.react_native:
        if args.metro_port == DEFAULT_WEB_PORT:
            parser.error(
                f"--metro-port cannot be {DEFAULT_WEB_PORT}: port {DEFAULT_WEB_PORT} is reserved for web servers and Cloudflare Tunnel."
            )
        if args.opencode and args.metro_port == args.opencode_port:
            parser.error(
                "--metro-port and --opencode-port must differ: a port can only be exposed once."
            )

    if args.t3 and args.t3_port == DEFAULT_WEB_PORT:
        parser.error(
            f"--t3-port cannot be {DEFAULT_WEB_PORT}: port {DEFAULT_WEB_PORT} is reserved for web servers and Cloudflare Tunnel."
        )

    if args.t3 and args.opencode and args.t3_port == args.opencode_port:
        parser.error(
            "--t3-port and --opencode-port must differ: a port can only be exposed once."
        )

    if args.t3 and args.react_native and args.t3_port == args.metro_port:
        parser.error(
            "--t3-port and --metro-port must differ: a port can only be exposed once."
        )

    pubkey_content = load_ssh_pub_key()

    if args.name:
        app_name = args.name
    else:
        bare_repo = clean_secret.split("/")[-1] if clean_secret else "sandbox"
        random_id = uuid.uuid4().hex[:8]
        app_prefix = "test-" if is_testing else ""
        app_name = f"{app_prefix}{bare_repo}-{random_id}"

    app = modal.App.lookup(app_name, create_if_missing=True)

    runtime_desc = "VM Sandbox" if args.vm else "Sandbox"

    browser_active = browser_enabled(
        browser=args.browser, opencode=args.opencode, agy=args.agy
    )

    if args.from_snapshot:
        image = modal.Image.from_id(args.from_snapshot)
    else:
        # Build the image incrementally based on the CLI flags passed.
        image = build_sandbox_image(
            opencode=args.opencode,
            agy=args.agy,
            browser=browser_active,
            modal_tooling=args.modal,
            react_native=args.react_native,
            t3=args.t3,
        )

    if secrets_dir:
        remote_secrets_dir = REMOTE_ORG_SECRETS_DIR if is_org else REMOTE_REPO_SECRETS_DIR
        image = image.add_local_dir(secrets_dir, remote_secrets_dir, copy=True)

    cloudflare_active = not args.no_cloudflare

    encrypted_ports: list[int] = []
    sandbox_secrets = [modal.Secret.from_name(SHARED_SECRET_NAME)]
    env: dict[str, str | None] = {
        "SSH_AUTHORIZED_KEY": pubkey_content,
        "PORT": str(DEFAULT_WEB_PORT),
        "HOSTNAME": "0.0.0.0",
        "APP_NAME": app_name,
    }
    if args.from_snapshot:
        env["RESUME_SNAPSHOT"] = "1"
    if target_repo:
        env["GH_REPO"] = target_repo
    if not cloudflare_active:
        env["ENABLE_CLOUDFLARE"] = "0"

    memory_gb: int | None = None
    if args.vm:
        memory_gb = args.memory if args.memory is not None else 1
        memory_mib = memory_gb * 1024
        swap_gb = memory_gb * 2
        env["SWAP_GB"] = str(swap_gb)
        env["ENABLE_DOCKER"] = "1"

    opencode_password = None
    if args.opencode:
        encrypted_ports.append(args.opencode_port)
        # Fresh password per launch, so nothing has to be pre-provisioned in the secret.
        opencode_password = secrets.token_urlsafe(16)
        sandbox_secrets.append(
            modal.Secret.from_dict({"OPENCODE_SERVER_PASSWORD": opencode_password})
        )
        # Explicit trigger for startup.sh; OPENCODE_PORT is only the port value.
        env["ENABLE_OPENCODE"] = "1"
        env["OPENCODE_PORT"] = str(args.opencode_port)

    if args.t3:
        encrypted_ports.append(args.t3_port)
        env["ENABLE_T3"] = "1"
        env["T3_PORT"] = str(args.t3_port)

    if args.agy:
        # Explicit trigger for startup.sh to export the antigravity PATH in SSH sessions.
        env["ENABLE_ANTIGRAVITY"] = "1"

    if args.modal:
        env["ENABLE_MODAL"] = "1"

    if args.sops:
        env["ENABLE_SOPS"] = "1"

    if browser_active:
        env["ENABLE_BROWSER"] = "1"

    volumes = {}
    if args.react_native:
        encrypted_ports.append(args.metro_port)
        env["ENABLE_REACT_NATIVE"] = "1"
        env["METRO_PORT"] = str(args.metro_port)
        volumes.update(get_gradle_volumes())

    features = []
    if not args.no_cloudflare:
        features.append("Cloudflare Tunnel")
    if args.react_native:
        features.append("React Native")
    if args.agy:
        features.append("Antigravity")
    if args.opencode:
        features.append("OpenCode")
    if args.t3:
        features.append("T3 Code")
    if args.modal:
        features.append("Modal")
    if args.sops:
        features.append("SOPS")
    if browser_active:
        features.append("Browser")

    features_suffix = f" & {' & '.join(features)}" if features else ""
    from_suffix = f" from snapshot {args.from_snapshot}" if args.from_snapshot else ""
    print(
        f"🏝️  Launching Modal {runtime_desc}{from_suffix} with SSH"
        f"{features_suffix} (App: {app_name})..."
    )

    sandbox_kwargs: dict = {
        "timeout": TIMEOUT_SECS,
        "idle_timeout": IDLE_TIMEOUT_SECS,
        "image": image,
        "app": app,
        "volumes": volumes,
        "unencrypted_ports": [22],
        "encrypted_ports": encrypted_ports,
        "cpu": (0.125, 4.0),
        "env": env,
    }
    if args.vm:
        sandbox_kwargs["memory"] = memory_mib
        sandbox_kwargs["experimental_options"] = {"vm_runtime": True}
    else:
        sandbox_kwargs["memory"] = (128, 16384)

    with modal.enable_output():
        sandbox = modal.Sandbox.create(
            "bash",
            REMOTE_STARTUP_SCRIPT,
            args.github_branch,
            secrets=sandbox_secrets,
            **sandbox_kwargs,
        )

    # Retrieve forwarded tunnels
    ssh_info = None
    opencode_url = None
    metro_url = None
    t3_url = None
    try:
        tunnels = sandbox.tunnels()
        if 22 in tunnels:
            ssh_info = tunnels[22].tcp_socket
        if args.opencode and args.opencode_port in tunnels:
            opencode_url = tunnels[args.opencode_port].url
        if args.react_native and args.metro_port in tunnels:
            metro_url = tunnels[args.metro_port].url
        if args.t3 and args.t3_port in tunnels:
            t3_url = tunnels[args.t3_port].url
    except Exception as exc:
        print(f"⚠️  Could not obtain tunnel metadata: {exc}")

    t3_pair_url = None
    t3_qr_code = None
    if args.t3 and t3_url:
        # Mint the 24-hour pairing token directly from the container's pre-baked t3 binary
        try:
            proc = sandbox.exec("t3", "auth", "pairing", "create", "--ttl", "24h", "--json")
            if proc.wait() == 0:
                out = proc.stdout.read().strip()
                if out:
                    pairing_data = json.loads(out)
                    credential = pairing_data.get("credential")
                    if credential:
                        t3_pair_url = f"{t3_url}/pair#token={credential}"
                        t3_qr_code = generate_ascii_qr(t3_pair_url)
        except Exception:
            pass

        # Fallback to /tmp/t3-pairing.json if direct exec failed
        if not t3_pair_url:
            for _ in range(6):
                try:
                    proc = sandbox.exec("cat", "/tmp/t3-pairing.json")
                    if proc.wait() == 0:
                        out = proc.stdout.read().strip()
                        if out:
                            pairing_data = json.loads(out)
                            credential = pairing_data.get("credential")
                            if credential:
                                t3_pair_url = f"{t3_url}/pair#token={credential}"
                                t3_qr_code = generate_ascii_qr(t3_pair_url)
                                break
                except Exception:
                    pass
                time.sleep(0.5)

        if not t3_pair_url:
            t3_pair_url = t3_url

    print_access_info(
        sandbox,
        app_name,
        ssh_info=ssh_info,
        opencode_url=opencode_url,
        opencode_port=args.opencode_port if args.opencode else None,
        opencode_password=opencode_password,
        metro_url=metro_url,
        metro_port=args.metro_port if args.react_native else None,
        t3_url=t3_url,
        t3_port=args.t3_port if args.t3 else None,
        t3_pair_url=t3_pair_url,
        t3_qr_code=t3_qr_code,
        memory_gb=memory_gb,
        agy_enabled=args.agy,
        cloudflare_enabled=not args.no_cloudflare,
        sops_enabled=args.sops,
    )


def main():
    parser = create_parser()
    args = parser.parse_args()
    validate_args(parser, args)

    if args.snapshot:
        capture_snapshot(
            sandbox_id=args.snapshot,
            ttl_days=args.snapshot_ttl,
            terminate=args.terminate,
        )
        return

    run_sandbox_launch(args, parser=parser)


if __name__ == "__main__":
    main()

