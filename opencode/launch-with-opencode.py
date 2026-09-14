import argparse
from pathlib import Path
import secrets
import uuid
import modal

OPENCODE_PORT = 4096

# Paths
LOCAL_CONFIG_PATH = Path(__file__).parent / "opencode.json"
REMOTE_CONFIG_PATH = "/root/.config/opencode/opencode.json"

LOCAL_STARTUP_SCRIPT = Path(__file__).parent / "startup.sh"
REMOTE_STARTUP_SCRIPT = "/root/startup.sh"

LOCAL_GIT_BASH = Path(__file__).resolve().parent.parent / "git.bash"
REMOTE_GIT_BASH = "/root/.git.bash"

DEFAULT_SSH_KEY = Path(__file__).parent / "id_ed25519"

# Static base image: built once and cached by Modal
base_image = (
    modal.Image.from_registry("node:24-bookworm-slim")
    .env({"DEBIAN_FRONTEND": "noninteractive"})
    .apt_install(
        "curl",
        "git",
        "gh",
        "htop",
        "openssh-server",
        "wget",
    )
    .run_commands(
        "corepack enable pnpm",
        "corepack prepare pnpm@10.31.0 --activate",
        "curl -fsSL https://opencode.ai/install | bash",
        "mkdir -p /run/sshd /root/.ssh /etc/ssh/sshd_config.d",
        "echo 'PermitRootLogin prohibit-password' > /etc/ssh/sshd_config.d/modal.conf",
        "echo 'PubkeyAuthentication yes' >> /etc/ssh/sshd_config.d/modal.conf",
        "echo 'PasswordAuthentication no' >> /etc/ssh/sshd_config.d/modal.conf",
        "ssh-keygen -A",
    )
    .env({
        "PATH": "/root/.opencode/bin:${PATH}",
        "OPENCODE_PORT": str(OPENCODE_PORT),
    })
)

# Optional local OpenCode configuration
if LOCAL_CONFIG_PATH.exists():
    base_image = base_image.add_local_file(
        LOCAL_CONFIG_PATH, REMOTE_CONFIG_PATH, copy=True
    )

if LOCAL_GIT_BASH.exists():
    base_image = base_image.add_local_file(
        LOCAL_GIT_BASH, REMOTE_GIT_BASH, copy=True
    )

# Bundle startup script into the image
base_image = base_image.add_local_file(
    LOCAL_STARTUP_SCRIPT, REMOTE_STARTUP_SCRIPT, copy=True
)


def load_ssh_pubkey(key_path_str: str) -> tuple[str, Path]:
    """Loads SSH public key content and returns (pubkey_content, private_key_path)."""
    p = Path(key_path_str).expanduser()
    if p.suffix == ".pub":
        pub_path = p
        priv_path = p.with_suffix("")
    else:
        pub_path = p.with_name(p.name + ".pub")
        priv_path = p

    if not pub_path.exists():
        if p.exists() and p.read_text().startswith("ssh-"):
            return p.read_text().strip(), priv_path
        raise FileNotFoundError(f"SSH public key not found at {pub_path} or {p}")

    return pub_path.read_text().strip(), priv_path


def parse_timeout(timeout_str: str) -> int:
    """Parses human-friendly timeout (e.g. '2h', '90m', '12') into seconds."""
    if timeout_str.endswith("h"):
        minutes = int(timeout_str[:-1]) * 60
    elif timeout_str.endswith("m"):
        minutes = int(timeout_str[:-1])
    else:
        minutes = int(timeout_str) * 60

    if not (1 <= minutes <= 24 * 60):
        raise argparse.ArgumentTypeError("Timeout must be between 1 minute and 24 hours.")
    return minutes * 60


def print_access_info(
    sandbox: modal.Sandbox,
    app_name: str,
    password: str,
    ssh_info: tuple[str, int] | None = None,
    private_key_path: Path | None = None,
):
    tunnel = None
    try:
        tunnels = sandbox.tunnels()
        if OPENCODE_PORT in tunnels:
            tunnel = tunnels[OPENCODE_PORT]
    except Exception as exc:
        print(f"⚠️  Could not obtain tunnel metadata: {exc}")

    print("\n" + "=" * 60)
    print("🏖️  OpenCode Sandbox Ready!")
    print(f"  • App:      {app_name}")
    if tunnel:
        print(f"  • WebUI:    {tunnel.url} (User: opencode)")
        print(f"  • Password: {password}")
        print(f"  • Attach:   OPENCODE_SERVER_PASSWORD={password} opencode attach {tunnel.url}")
    print(f"  • Shell:    modal shell {sandbox.object_id}")
    if ssh_info:
        ssh_host, ssh_port = ssh_info
        key_arg = (
            f"-i {private_key_path} "
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
        print(f"  User root")
        if private_key_path and private_key_path.exists():
            print(f"  IdentityFile {private_key_path.resolve()}")
        print("  StrictHostKeyChecking no")
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Launch OpenCode server in a Modal Sandbox with SSH"
    )
    parser.add_argument(
        "--timeout",
        default="12",
        help="Timeout (e.g., 2h, 90m, or raw hours). Default: 12h",
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
        "--ssh-key",
        default=str(DEFAULT_SSH_KEY),
        help=f"Path to SSH key (default: {DEFAULT_SSH_KEY})",
    )
    args = parser.parse_args()

    pubkey_content, priv_key_path = load_ssh_pubkey(args.ssh_key)

    random_id = uuid.uuid4().hex[:8]
    app_name = f"{args.secret_collection}-{random_id}"
    server_password = secrets.token_urlsafe(16)

    app = modal.App.lookup(app_name, create_if_missing=True)
    secret = modal.Secret.from_name(args.secret_collection)
    password_secret = modal.Secret.from_dict(
        {"OPENCODE_SERVER_PASSWORD": server_password}
    )

    print(f"🏖️  Launching Modal Sandbox with OpenCode & SSH (App: {app_name})...")
    with modal.enable_output():
        sandbox = modal.Sandbox.create(
            "bash",
            REMOTE_STARTUP_SCRIPT,
            args.github_ref,
            encrypted_ports=[OPENCODE_PORT],
            unencrypted_ports=[22],
            secrets=[secret, password_secret],
            timeout=parse_timeout(args.timeout),
            image=base_image,
            app=app,
            env={
                "SSH_AUTHORIZED_KEY": pubkey_content,
            },
        )

    # Retrieve forwarded tunnels
    ssh_info = None
    try:
        tunnels = sandbox.tunnels()
        if 22 in tunnels:
            ssh_info = tunnels[22].tcp_socket
    except Exception as exc:
        print(f"⚠️  Could not obtain tunnel metadata: {exc}")

    print_access_info(
        sandbox,
        app_name,
        server_password,
        ssh_info=ssh_info,
        private_key_path=priv_key_path,
    )


if __name__ == "__main__":
    main()
