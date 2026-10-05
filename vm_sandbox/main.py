import argparse
from pathlib import Path
import secrets
import sys
import uuid

import modal

# Ensure repository root is on sys.path for shared imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.image import (
    REMOTE_STARTUP_SCRIPT,
    SHARED_SECRET_NAME,
    browser_enabled,
    build_sandbox_image,
    get_gradle_volumes,
    load_ssh_pub_key,
)

# Modal's default timeout for Sandbox.create is 300s (5 minutes) if omitted; max allowed is 24 hours.
TIMEOUT_SECS = 16 * 60 * 60  # 16 hours
IDLE_TIMEOUT_SECS = 4 * 60 * 60  # 4 hours
DEFAULT_OPENCODE_PORT = 4096
DEFAULT_METRO_PORT = 8081


def print_access_info(
    sandbox: modal.Sandbox,
    app_name: str,
    ssh_info: tuple[str, int] | None = None,
    web_url: str | None = None,
    web_port: int | None = None,
    opencode_url: str | None = None,
    opencode_port: int | None = None,
    opencode_password: str | None = None,
    metro_url: str | None = None,
    metro_port: int | None = None,
    memory_gb: int | None = None,
    agy_enabled: bool = False,
):
    print("\n" + "=" * 60)
    print("🏝️  Sandbox Ready!")
    print(f"  • App:      {app_name}")
    print(f"  • Shell:    modal shell {sandbox.object_id}")
    if memory_gb:
        print(f"  • Memory:   {memory_gb} GB RAM + {memory_gb * 2} GB swap")
    if web_url:
        print(f"  • Web URL:  {web_url} (port {web_port})")
    if metro_url:
        print(f"  • Metro:    {metro_url} (port {metro_port})")
    if opencode_url:
        print(f"  • OpenCode: {opencode_url} (port {opencode_port}, User: opencode)")
        if opencode_password:
            print(f"  • Password: {opencode_password}")
            print(
                f"  • Attach:   OPENCODE_SERVER_PASSWORD={opencode_password} "
                f"opencode attach {opencode_url}"
            )
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
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Launch a repository in a Modal VM Sandbox with SSH & Web URL"
    )
    parser.add_argument(
        "--github-ref",
        default="main",
        help="Git ref to checkout (branch, tag, commit). Default: main",
    )
    parser.add_argument(
        "-s",
        "--secret",
        "--secret-collection",
        dest="secret_collection",
        required=True,
        help="Modal Secret collection name.",
    )

    parser.add_argument(
        "--web-port",
        type=int,
        default=3000,
        help="Web application port to expose over public HTTPS URL (default: 3000)",
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
        help="Also set up antigravity-cli and launch the background Antigravity Remote Control daemon (mounts shared settings & keybindings and automatically enables SOPS secret decryption).",
    )
    parser.add_argument(
        "--opencode-port",
        type=int,
        default=DEFAULT_OPENCODE_PORT,
        help=f"Port for the OpenCode server, only used with --opencode (default: {DEFAULT_OPENCODE_PORT})",
    )
    parser.add_argument(
        "--react-native",
        action="store_true",
        help="Also configure Android SDK, NDK, OpenJDK 17, Gradle cache volumes, and Metro bundler port forwarding for React Native.",
    )
    parser.add_argument(
        "--metro-port",
        type=int,
        default=DEFAULT_METRO_PORT,
        help=f"Port for the React Native Metro bundler, only used with --react-native (default: {DEFAULT_METRO_PORT})",
    )
    parser.add_argument(
        "--modal",
        action="store_true",
        help="Also configure Python 3, virtual environment, Modal SDK, and decrypt Modal client credentials.",
    )
    parser.add_argument(
        "--memory",
        type=int,
        default=1,
        metavar="GB",
        help="RAM to allocate in GB (1 -> 1 GB, 2 -> 2 GB, ...). Swap is 2x RAM. Default: 1",
    )
    args = parser.parse_args()

    if args.memory < 1:
        parser.error("--memory must be a positive integer number of GB.")

    active_ports = {"--web-port": args.web_port}
    if args.opencode:
        if args.opencode_port in active_ports.values():
            parser.error(
                "--opencode-port and --web-port must differ: a port can only be exposed once."
            )
        active_ports["--opencode-port"] = args.opencode_port

    if args.react_native:
        if args.metro_port in active_ports.values():
            conflicting_flag = [
                flag for flag, port in active_ports.items() if port == args.metro_port
            ][0]
            parser.error(
                f"--metro-port and {conflicting_flag} must differ: a port can only be exposed once."
            )
        active_ports["--metro-port"] = args.metro_port

    memory_mib = args.memory * 1024
    swap_gb = args.memory * 2

    pubkey_content = load_ssh_pub_key()

    random_id = uuid.uuid4().hex[:8]
    app_name = f"{args.secret_collection}-{random_id}"

    app = modal.App.lookup(app_name, create_if_missing=True)
    secret = modal.Secret.from_name(args.secret_collection)

    experimental_options = {"vm_runtime": True}
    runtime_desc = "VM Sandbox"

    browser_active = browser_enabled(
        browser=args.browser, opencode=args.opencode, agy=args.agy
    )

    # Build the image incrementally based on the CLI flags passed.
    image = build_sandbox_image(
        opencode=args.opencode,
        agy=args.agy,
        browser=browser_active,
        modal_tooling=args.modal,
        react_native=args.react_native,
    )

    encrypted_ports = [args.web_port]
    sandbox_secrets = [secret]
    if args.agy or args.modal or args.opencode:
        sandbox_secrets.append(modal.Secret.from_name(SHARED_SECRET_NAME))
    env: dict[str, str | None] = {
        "SSH_AUTHORIZED_KEY": pubkey_content,
        "PORT": str(args.web_port),
        "HOSTNAME": "0.0.0.0",
        "SWAP_GB": str(swap_gb),
        "ENABLE_DOCKER": "1",
        "APP_NAME": app_name,
    }

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

    if args.agy:
        # Explicit trigger for startup.sh to export the antigravity PATH in SSH sessions.
        env["ENABLE_ANTIGRAVITY"] = "1"

    if args.modal:
        env["ENABLE_MODAL"] = "1"

    if browser_active:
        env["ENABLE_BROWSER"] = "1"

    volumes = {}
    if args.react_native:
        encrypted_ports.append(args.metro_port)
        env["ENABLE_REACT_NATIVE"] = "1"
        env["METRO_PORT"] = str(args.metro_port)
        volumes.update(get_gradle_volumes())

    features: list[str] = []
    if args.react_native:
        features.append("React Native")
    if args.agy:
        features.append("Antigravity")
    if args.opencode:
        features.append("OpenCode")
    if args.modal:
        features.append("Modal")
    if browser_active:
        features.append("Browser")

    features_suffix = f" & {' & '.join(features)}" if features else ""
    print(
        f"🏝️  Launching Modal {runtime_desc} with SSH & Web Port {args.web_port}"
        f"{features_suffix} (App: {app_name})..."
    )
    with modal.enable_output():
        sandbox = modal.Sandbox.create(
            "bash",
            REMOTE_STARTUP_SCRIPT,
            args.github_ref,
            secrets=sandbox_secrets,
            timeout=TIMEOUT_SECS,
            idle_timeout=IDLE_TIMEOUT_SECS,
            image=image,
            app=app,
            volumes=volumes,
            # cpu and memory are set explicitly below. Modal's VM defaults would be a
            # 1024 MiB (1 GiB) memory request and a 0.125 physical core CPU request.
            # CPU format: (request, limit) in physical CPU cores (1 physical core ≈ 2 vCPUs).
            # - Default request: 0.125 (1/8 core). Default soft limit: request + 16 cores (16.125).
            # - Highest maximum: Bounded by Modal host worker capacity (typically up to ~64-128 physical cores).
            #   Exceeding host capacity raises InvalidError at creation time.
            # Memory format: (request, limit) in MiB.
            # - Highest maximum: Bounded by Modal host worker RAM (typically up to ~256-512 GiB / ~262,144-524,288 MiB).
            #   Exceeding host capacity raises InvalidError; exceeding limit at runtime causes OOM kill.
            # Swap is 10x to 50x slower than real RAM; keep it between 1× and 2× physical RAM.
            #   ./startup.sh allocates a swapfile of 2× the VM RAM (SWAP_GB env var).
            cpu=(0.125, 4.0),
            # VM sandboxes do not get dynamically expandable RAM, so memory must be a single
            # int (MiB): memory=(1024, 4096) would still cap the VM at the 1024 MiB request.
            # --memory N (GB) maps to N * 1024 MiB here.
            memory=memory_mib,
            experimental_options=experimental_options,
            unencrypted_ports=[22],
            encrypted_ports=encrypted_ports,
            env=env,
        )

    # Retrieve forwarded tunnels
    ssh_info = None
    web_url = None
    opencode_url = None
    metro_url = None
    try:
        tunnels = sandbox.tunnels()
        if 22 in tunnels:
            ssh_info = tunnels[22].tcp_socket
        if args.web_port in tunnels:
            web_url = tunnels[args.web_port].url
        if args.opencode and args.opencode_port in tunnels:
            opencode_url = tunnels[args.opencode_port].url
        if args.react_native and args.metro_port in tunnels:
            metro_url = tunnels[args.metro_port].url
    except Exception as exc:
        print(f"⚠️  Could not obtain tunnel metadata: {exc}")

    #  print the startup progress in your terminal in real time
    for line in sandbox.stdout:
        print(line, end="")
        if "Sandbox Ready" in line:
            break

    print_access_info(
        sandbox,
        app_name,
        ssh_info=ssh_info,
        web_url=web_url,
        web_port=args.web_port,
        opencode_url=opencode_url,
        opencode_port=args.opencode_port if args.opencode else None,
        opencode_password=opencode_password,
        metro_url=metro_url,
        metro_port=args.metro_port if args.react_native else None,
        memory_gb=args.memory,
        agy_enabled=args.agy,
    )


if __name__ == "__main__":
    main()
