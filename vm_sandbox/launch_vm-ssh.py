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
    modal.Image.from_registry("ubuntu:24.04")
    # Silently accepts default answers (or preseeded values) and never prompts the user.
    # If an issue requires manual intervention, it logs the error rather than waiting indefinitely.
    .env({"DEBIAN_FRONTEND": "noninteractive"})
    # wget is necessary for connecting vscode or antigravity-ide via ssh; not required for zed-editor
    # `docker.io`, `docker-buildx` for docker
    # unzip for fnm
    .apt_install(
        "curl",
        "git",
        "htop",
        "openssh-server",
        "wget",
        "docker.io",
        "docker-buildx",
        "unzip",
    )
    .run_commands(
        # Download and install fnm:
        "curl -o- https://fnm.vercel.app/install | bash",
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
    memory_gb: int | None = None,
):
    print("\n" + "=" * 60)
    print("🏝️  Sandbox Ready!")
    print(f"  • App:     {app_name}")
    print(f"  • Shell:   modal shell {sandbox.object_id}")
    if memory_gb:
        print(f"  • Memory:  {memory_gb} GB RAM + {memory_gb * 2} GB swap")
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
        "--memory",
        type=int,
        default=1,
        metavar="GB",
        help="RAM to allocate in GB (1 -> 1 GB, 2 -> 2 GB, ...). Swap is 2x RAM. Default: 1",
    )
    args = parser.parse_args()

    if args.memory < 1:
        parser.error("--memory must be a positive integer number of GB.")

    memory_mib = args.memory * 1024
    swap_gb = args.memory * 2

    pubkey_content, priv_key_path = load_ssh_pubkey(args.ssh_key)

    random_id = uuid.uuid4().hex[:8]
    app_name = f"{args.secret_collection}-{random_id}"

    app = modal.App.lookup(app_name, create_if_missing=True)
    secret = modal.Secret.from_name(args.secret_collection)

    experimental_options = {"vm_runtime": True}
    runtime_desc = "VM Sandbox"

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
            encrypted_ports=[args.web_port],
            env={
                "SSH_AUTHORIZED_KEY": pubkey_content,
                "PORT": str(args.web_port),
                "HOSTNAME": "0.0.0.0",
                "SWAP_GB": str(swap_gb),
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
        memory_gb=args.memory,
    )


if __name__ == "__main__":
    main()
