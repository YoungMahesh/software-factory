import argparse
import uuid
from pathlib import Path

import modal

LOCAL_STARTUP_SCRIPT = Path(__file__).parent / "startup.sh"
REMOTE_STARTUP_SCRIPT = "/root/startup.sh"
LOCAL_GIT_BASH = Path(__file__).resolve().parent.parent / "git.bash"
REMOTE_GIT_BASH = "/root/.git.bash"
DEFAULT_SSH_KEY = Path(__file__).parent / "id_ed25519"
# Modal's default timeout for Sandbox.create is 300s (5 minutes) if omitted; max allowed is 24 hours.
TIMEOUT_SECS = 12 * 60 * 60  # 12 hours


# Static base image: built once and cached by Modal
base_image = (
    modal.Image.from_registry("node:24-bookworm-slim")
    # Silently accepts default answers (or preseeded values) and never prompts the user.
    # If an issue requires manual intervention, it logs the error rather than waiting indefinitely.
    .env({"DEBIAN_FRONTEND": "noninteractive"})
    # wget is necessary for connecting vscode or antigravity-ide via ssh; not required for zed-editor
    .apt_install(
        "curl",
        "git",
        "htop",
        "openssh-server",
        "wget",
    )
    .run_commands(
        "corepack enable pnpm",
        "corepack prepare pnpm@10.31.0 --activate",
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


def print_access_info(
    sandbox: modal.Sandbox,
    app_name: str,
    ssh_info: tuple[str, int] | None = None,
    private_key_path: Path | None = None,
    web_url: str | None = None,
    web_port: int | None = None,
):
    print("\n" + "=" * 60)
    print("🏝️  Sandbox Ready!")
    print(f"  • App:     {app_name}")
    print(f"  • Shell:   modal shell {sandbox.object_id}")
    if web_url:
        print(f"  • Web URL: {web_url} (port {web_port})")
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
        print(f"  • SSH:     {ssh_cmd}")
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
        description="Launch a repository in a Modal Sandbox with SSH & Web URL"
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
    parser.add_argument(
        "--web-port",
        type=int,
        default=3000,
        help="Web application port to expose over public HTTPS URL (default: 3000)",
    )
    parser.add_argument(
        "--vm",
        action="store_true",
        help="Launch inside a VM Sandbox with full Linux kernel (default: standard container sandbox)",
    )
    args = parser.parse_args()

    pubkey_content, priv_key_path = load_ssh_pubkey(args.ssh_key)

    random_id = uuid.uuid4().hex[:8]
    app_name = f"{args.secret_collection}-{random_id}"

    app = modal.App.lookup(app_name, create_if_missing=True)
    secret = modal.Secret.from_name(args.secret_collection)

    experimental_options = {"vm_runtime": True} if args.vm else None
    runtime_desc = "VM Sandbox" if args.vm else "Standard Sandbox"

    print(
        f"🏝️  Launching Modal {runtime_desc} with SSH & Web Port {args.web_port} (App: {app_name})..."
    )
    with modal.enable_output():
        sandbox = modal.Sandbox.create(
            "bash",
            REMOTE_STARTUP_SCRIPT,
            args.github_ref,
            secrets=[secret],
            timeout=TIMEOUT_SECS,
            image=base_image,
            app=app,
            experimental_options=experimental_options,
            unencrypted_ports=[22],
            encrypted_ports=[args.web_port],
            env={
                "SSH_AUTHORIZED_KEY": pubkey_content,
                "PORT": str(args.web_port),
                "HOSTNAME": "0.0.0.0",
            },
        )

    # Retrieve forwarded tunnels
    ssh_info = None
    web_url = None
    try:
        tunnels = sandbox.tunnels()
        if 22 in tunnels:
            ssh_info = tunnels[22].tcp_socket
        if args.web_port in tunnels:
            web_url = tunnels[args.web_port].url
    except Exception as exc:
        print(f"⚠️  Could not obtain tunnel metadata: {exc}")

    print_access_info(
        sandbox,
        app_name,
        ssh_info=ssh_info,
        private_key_path=priv_key_path,
        web_url=web_url,
        web_port=args.web_port,
    )


if __name__ == "__main__":
    main()
