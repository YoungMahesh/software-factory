import argparse
from pathlib import Path
import secrets
import uuid

import modal

LOCAL_STARTUP_SCRIPT = Path(__file__).parent / "startup.sh"
REMOTE_STARTUP_SCRIPT = "/root/startup.sh"
LOCAL_GIT_BASH = Path(__file__).resolve().parent.parent / "git.bash"
REMOTE_GIT_BASH = "/root/.git.bash"
SHARED_DIR = Path(__file__).resolve().parent.parent / "shared"
LOCAL_OPENCODE_CONFIG = SHARED_DIR / "opencode.json"
REMOTE_OPENCODE_CONFIG = "/root/.config/opencode/opencode.json"
LOCAL_ANTIGRAVITY_SETTINGS = SHARED_DIR / "antigravity-settings.json"
REMOTE_ANTIGRAVITY_SETTINGS = "/root/.gemini/antigravity-cli/settings.json"
LOCAL_ANTIGRAVITY_KEYBINDINGS = SHARED_DIR / "antigravity-keybindings.json"
REMOTE_ANTIGRAVITY_KEYBINDINGS = "/root/.gemini/antigravity-cli/keybindings.json"
SHARED_SSH_PUB_KEY = SHARED_DIR / "ssh-key.pub"
HOST_SSH_PRIV_KEY = Path.home() / ".ssh" / "modal-sandbox"
# Modal's default timeout for Sandbox.create is 300s (5 minutes) if omitted; max allowed is 24 hours.
TIMEOUT_SECS = 16 * 60 * 60  # 16 hours
IDLE_TIMEOUT_SECS = 4 * 60 * 60  # 4 hours
DEFAULT_OPENCODE_PORT = 4096


# Static base image: built once and cached by Modal
base_image = (
    modal.Image.from_registry("ubuntu:24.04")
    # Silently accepts default answers (or preseeded values) and never prompts the user.
    # If an issue requires manual intervention, it logs the error rather than waiting indefinitely.
    .env({"DEBIAN_FRONTEND": "noninteractive"})
    # wget is necessary for connecting vscode or antigravity-ide via ssh; not required for zed-editor
    # `docker.io`, `docker-buildx` for docker
    # unzip for fnm
    # ripgrep: ai agents use this tool to search text in codebase
    .apt_install(
        "curl",
        "git",
        "htop",
        "openssh-server",
        "wget",
        "docker.io",
        "docker-buildx",
        "unzip",
        "ripgrep",
        "age",
    )
    .run_commands(
        # Download and install fnm:
        "curl -o- https://fnm.vercel.app/install | bash",
        "curl -fsSL https://github.com/getsops/sops/releases/download/v3.13.3/sops-v3.13.3.linux.amd64 -o /usr/local/bin/sops",
        "chmod +x /usr/local/bin/sops",
        "mkdir -p /run/sshd /root/.ssh /etc/ssh/sshd_config.d",
        "echo 'PermitRootLogin prohibit-password' > /etc/ssh/sshd_config.d/modal.conf",
        "echo 'PubkeyAuthentication yes' >> /etc/ssh/sshd_config.d/modal.conf",
        "echo 'PasswordAuthentication no' >> /etc/ssh/sshd_config.d/modal.conf",
        "ssh-keygen -A",
    )
    .add_local_file(LOCAL_STARTUP_SCRIPT, REMOTE_STARTUP_SCRIPT, copy=True)
)

if LOCAL_GIT_BASH.exists():
    base_image = base_image.add_local_file(LOCAL_GIT_BASH, REMOTE_GIT_BASH, copy=True)


def load_ssh_key_pair() -> tuple[str, Path]:
    """Loads SSH public key content and validates the host private key.

    Returns (pubkey_content, host_private_key_path).
    Raises FileNotFoundError if the public key or host private key is missing.
    """
    if not SHARED_SSH_PUB_KEY.exists():
        raise FileNotFoundError(
            f"SSH public key not found at {SHARED_SSH_PUB_KEY}."
        )
    if not HOST_SSH_PRIV_KEY.exists():
        raise FileNotFoundError(
            f"SSH private key not found at {HOST_SSH_PRIV_KEY}. Please run 'bash scripts/setup.sh' to decrypt it."
        )
    return SHARED_SSH_PUB_KEY.read_text().strip(), HOST_SSH_PRIV_KEY


def print_access_info(
    sandbox: modal.Sandbox,
    app_name: str,
    ssh_info: tuple[str, int] | None = None,
    private_key_path: Path | None = None,
    web_url: str | None = None,
    web_port: int | None = None,
    opencode_url: str | None = None,
    opencode_port: int | None = None,
    opencode_password: str | None = None,
    memory_gb: int | None = None,
):
    print("\n" + "=" * 60)
    print("🏝️  Sandbox Ready!")
    print(f"  • App:      {app_name}")
    print(f"  • Shell:    modal shell {sandbox.object_id}")
    if memory_gb:
        print(f"  • Memory:   {memory_gb} GB RAM + {memory_gb * 2} GB swap")
    if web_url:
        print(f"  • Web URL:  {web_url} (port {web_port})")
    if opencode_url:
        print(f"  • OpenCode: {opencode_url} (port {opencode_port}, User: opencode)")
        if opencode_password:
            print(f"  • Password: {opencode_password}")
            print(
                f"  • Attach:   OPENCODE_SERVER_PASSWORD={opencode_password} "
                f"opencode attach {opencode_url}"
            )
    if ssh_info:
        ssh_host, ssh_port = ssh_info
        key_display = (
            f"~/{private_key_path.relative_to(Path.home())}"
            if private_key_path and private_key_path.is_relative_to(Path.home())
            else str(private_key_path)
        )
        key_arg = (
            f"-i {key_display} "
            if private_key_path and private_key_path.exists()
            else ""
        )
        ssh_cmd = (
            f"ssh {key_arg}-o StrictHostKeyChecking=no -p {ssh_port} root@{ssh_host}"
        )
        print(f"  • SSH:      {ssh_cmd}")
        print("\nVS Code / SSH Config snippet:")
        print(f"Host {app_name}")
        print(f"  HostName {ssh_host}")
        print(f"  Port {ssh_port}")
        print("  User root")
        if private_key_path and private_key_path.exists():
            print(f"  IdentityFile {key_display}")
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
        "--agy",
        action="store_true",
        help="Also set up antigravity-cli in the sandbox (mounts shared settings & keybindings and automatically enables SOPS secret decryption).",
    )
    parser.add_argument(
        "--opencode-port",
        type=int,
        default=DEFAULT_OPENCODE_PORT,
        help=f"Port for the OpenCode server, only used with --opencode (default: {DEFAULT_OPENCODE_PORT})",
    )
    parser.add_argument(
        "--memory",
        type=int,
        default=1,
        metavar="GB",
        help="RAM to allocate in GB (1 -> 1 GB, 2 -> 2 GB, ...). Swap is 2x RAM. Default: 1",
    )
    parser.add_argument(
        "--sops",
        action="store_true",
        help="Configure SOPS age key from AGE_PRIVATE_KEY secret and run scripts/setup.sh if present.",
    )
    args = parser.parse_args()

    if args.memory < 1:
        parser.error("--memory must be a positive integer number of GB.")

    if args.opencode and args.opencode_port == args.web_port:
        parser.error(
            "--opencode-port and --web-port must differ: a port can only be exposed once."
        )

    memory_mib = args.memory * 1024
    swap_gb = args.memory * 2

    pubkey_content, priv_key_path = load_ssh_key_pair()

    random_id = uuid.uuid4().hex[:8]
    app_name = f"{args.secret_collection}-{random_id}"

    app = modal.App.lookup(app_name, create_if_missing=True)
    secret = modal.Secret.from_name(args.secret_collection)

    experimental_options = {"vm_runtime": True}
    runtime_desc = "VM Sandbox"

    # Build the image incrementally based on the CLI flags passed. Layers are only
    # added (and built/cached by Modal) for the features actually requested.
    image = base_image
    path_prefixes: list[str] = []

    if args.opencode:
        image = image.run_commands("curl -fsSL https://opencode.ai/install | bash")
        path_prefixes.append("/root/.opencode/bin")
        if LOCAL_OPENCODE_CONFIG.exists():
            image = image.add_local_file(
                LOCAL_OPENCODE_CONFIG, REMOTE_OPENCODE_CONFIG, copy=True
            )

    if args.agy:
        image = image.run_commands(
            "curl -fsSL https://antigravity.google/cli/install.sh | bash",
            "mkdir -p /root/.gemini/antigravity-cli",
        )
        path_prefixes.append("/root/.local/bin")
        if LOCAL_ANTIGRAVITY_SETTINGS.exists():
            image = image.add_local_file(
                LOCAL_ANTIGRAVITY_SETTINGS, REMOTE_ANTIGRAVITY_SETTINGS, copy=True
            )
        if LOCAL_ANTIGRAVITY_KEYBINDINGS.exists():
            image = image.add_local_file(
                LOCAL_ANTIGRAVITY_KEYBINDINGS, REMOTE_ANTIGRAVITY_KEYBINDINGS, copy=True
            )

    if path_prefixes:
        image = image.env({"PATH": ":".join(path_prefixes) + ":${PATH}"})

    encrypted_ports = [args.web_port]
    sandbox_secrets = [secret]
    env: dict[str, str | None] = {
        "SSH_AUTHORIZED_KEY": pubkey_content,
        "PORT": str(args.web_port),
        "HOSTNAME": "0.0.0.0",
        "SWAP_GB": str(swap_gb),
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

    if args.sops or args.agy:
        env["ENABLE_SOPS"] = "1"

    features: list[str] = []
    if args.agy:
        features.append("Antigravity")
    if args.opencode:
        features.append("OpenCode")
    if args.sops or args.agy:
        features.append("SOPS")

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
    try:
        tunnels = sandbox.tunnels()
        if 22 in tunnels:
            ssh_info = tunnels[22].tcp_socket
        if args.web_port in tunnels:
            web_url = tunnels[args.web_port].url
        if args.opencode and args.opencode_port in tunnels:
            opencode_url = tunnels[args.opencode_port].url
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
        private_key_path=priv_key_path,
        web_url=web_url,
        web_port=args.web_port,
        opencode_url=opencode_url,
        opencode_port=args.opencode_port if args.opencode else None,
        opencode_password=opencode_password,
        memory_gb=args.memory,
    )


if __name__ == "__main__":
    main()
