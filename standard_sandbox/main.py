import argparse
import secrets
import uuid
from pathlib import Path

import modal

LOCAL_STARTUP_SCRIPT = Path(__file__).parent / "startup.sh"
REMOTE_STARTUP_SCRIPT = "/root/startup.sh"
LOCAL_GIT_BASH = Path(__file__).resolve().parent.parent / "git.bash"
REMOTE_GIT_BASH = "/root/.git.bash"
LOCAL_OPENCODE_CONFIG = Path(__file__).parent / "opencode.json"
REMOTE_OPENCODE_CONFIG = "/root/.config/opencode/opencode.json"
LOCAL_ANTIGRAVITY_SETTINGS = Path(__file__).parent / "settings.json"
REMOTE_ANTIGRAVITY_SETTINGS = "/root/.gemini/antigravity-cli/settings.json"
LOCAL_ANTIGRAVITY_KEYBINDINGS = Path(__file__).parent / "keybindings.json"
REMOTE_ANTIGRAVITY_KEYBINDINGS = "/root/.gemini/antigravity-cli/keybindings.json"
LOCAL_ANTIGRAVITY_TOKEN = Path(__file__).parent / "antigravity-oauth-token"
REMOTE_ANTIGRAVITY_TOKEN = "/root/.gemini/antigravity-cli/antigravity-oauth-token"
DEFAULT_SSH_KEY = Path(__file__).parent / "id_ed25519"
# Modal's default timeout for Sandbox.create is 300s (5 minutes) if omitted; max allowed is 24 hours.
TIMEOUT_SECS = 16 * 60 * 60  # 16 hours
IDLE_TIMEOUT_SECS = 4 * 60 * 60  # 4 hours
DEFAULT_OPENCODE_PORT = 4096
DEFAULT_METRO_PORT = 8081

gradle_cache_vol = modal.Volume.from_name("gradle-caches", create_if_missing=True)
gradle_wrapper_vol = modal.Volume.from_name("gradle-wrapper", create_if_missing=True)
GRADLE_CACHE_PATH = "/root/.gradle/caches"
GRADLE_WRAPPER_PATH = "/root/.gradle/wrapper"

# Static base image: built once and cached by Modal
base_image = (
    modal.Image.from_registry("node:24.21-bookworm-slim")
    # Silently accepts default answers (or preseeded values) and never prompts the user.
    # If an issue requires manual intervention, it logs the error rather than waiting indefinitely.
    .env({"DEBIAN_FRONTEND": "noninteractive"})
    # wget is necessary for connecting vscode or antigravity-ide via ssh; not required for zed-editor
    # ripgrep: ai agents use this tool to search text in codebase
    .apt_install("curl", "git", "htop", "openssh-server", "wget", "ripgrep")
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
    opencode_url: str | None = None,
    opencode_port: int | None = None,
    opencode_password: str | None = None,
    metro_url: str | None = None,
    metro_port: int | None = None,
):
    print("\n" + "=" * 60)
    print("🏝️  Sandbox Ready!")
    print(f"  • App:      {app_name}")
    print(f"  • Shell:    modal shell {sandbox.object_id}")
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
                f"opencode --server {opencode_url}"
            )
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
        print("  User root")
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
        "--opencode",
        action="store_true",
        help="Also run an OpenCode server in the sandbox and expose its WebUI over public HTTPS URL.",
    )
    parser.add_argument(
        "--agy",
        action="store_true",
        help="Also set up antigravity-cli in the sandbox (with settings, keybindings and OAuth token if present).",
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
    args = parser.parse_args()

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

    pubkey_content, priv_key_path = load_ssh_pubkey(args.ssh_key)

    random_id = uuid.uuid4().hex[:8]
    app_name = f"{args.secret_collection}-{random_id}"

    app = modal.App.lookup(app_name, create_if_missing=True)
    secret = modal.Secret.from_name(args.secret_collection)

    # Build the image incrementally based on the CLI flags passed. Layers are only
    # added (and built/cached by Modal) for the features actually requested.
    image = base_image
    path_prefixes: list[str] = []

    if args.opencode:
        image = image.run_commands("curl -fsSL https://opencode.ai/v2/install | bash")
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
        if LOCAL_ANTIGRAVITY_TOKEN.exists():
            image = image.add_local_file(
                LOCAL_ANTIGRAVITY_TOKEN, REMOTE_ANTIGRAVITY_TOKEN, copy=True
            )
        else:
            print(
                f"⚠️  {LOCAL_ANTIGRAVITY_TOKEN.name} not found; antigravity-cli will not be pre-authenticated."
            )

    if args.react_native:
        image = (
            image.apt_install("openjdk-17-jdk-headless", "unzip")
            .env(
                {
                    "ANDROID_HOME": "/opt/android-sdk",
                    "ANDROID_SDK_ROOT": "/opt/android-sdk",
                    "JAVA_HOME": "/usr/lib/jvm/java-17-openjdk-amd64",
                }
            )
            .run_commands(
                "mkdir -p /opt/android-sdk/cmdline-tools",
                "wget -q https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip -O /tmp/cmdline-tools.zip",
                "unzip -q /tmp/cmdline-tools.zip -d /opt/android-sdk/cmdline-tools",
                "mv /opt/android-sdk/cmdline-tools/cmdline-tools /opt/android-sdk/cmdline-tools/latest",
                "rm -f /tmp/cmdline-tools.zip",
                "yes | /opt/android-sdk/cmdline-tools/latest/bin/sdkmanager --licenses",
                "/opt/android-sdk/cmdline-tools/latest/bin/sdkmanager "
                '"platform-tools" '
                '"platforms;android-34" "build-tools;34.0.0" '
                '"platforms;android-35" "build-tools;35.0.0" '
                '"ndk;26.1.10909125" "cmake;3.22.1"',
            )
        )
        path_prefixes.extend(
            [
                "/opt/android-sdk/cmdline-tools/latest/bin",
                "/opt/android-sdk/platform-tools",
            ]
        )

    if path_prefixes:
        image = image.env({"PATH": ":".join(path_prefixes) + ":${PATH}"})

    encrypted_ports = [args.web_port]
    sandbox_secrets = [secret]
    env: dict[str, str | None] = {
        "SSH_AUTHORIZED_KEY": pubkey_content,
        "PORT": str(args.web_port),
        "HOSTNAME": "0.0.0.0",
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

    volumes = {}
    if args.react_native:
        encrypted_ports.append(args.metro_port)
        env["ENABLE_REACT_NATIVE"] = "1"
        env["METRO_PORT"] = str(args.metro_port)
        volumes[GRADLE_CACHE_PATH] = gradle_cache_vol
        volumes[GRADLE_WRAPPER_PATH] = gradle_wrapper_vol

    features = []
    if args.react_native:
        features.append("React Native")
    if args.agy:
        features.append("Antigravity")
    if args.opencode:
        features.append("OpenCode")

    features_suffix = f" & {' & '.join(features)}" if features else ""
    print(
        f"🏝️  Launching Modal Sandbox with SSH & Web Port {args.web_port}"
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
            unencrypted_ports=[22],
            encrypted_ports=encrypted_ports,
            # CPU format: (request, limit) in physical CPU cores (1 physical core ≈ 2 vCPUs).
            # - Default request: 0.125 (1/8 core). Default soft limit: request + 16 cores (16.125).
            # - Highest maximum: Bounded by Modal host worker capacity (typically up to ~64-128 physical cores).
            #   Exceeding host capacity raises InvalidError at creation time.
            cpu=(0.125, 4.0),
            # Memory format: (request, limit) in MiB.
            # - Default request: 128 MiB for standard container sandboxes.
            # - Highest maximum: Bounded by Modal host worker RAM (typically up to ~256-512 GiB / ~262,144-524,288 MiB).
            #   Exceeding host capacity raises InvalidError; exceeding limit at runtime causes OOM kill.
            memory=(128, 16384),
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
        metro_url=metro_url,
        metro_port=args.metro_port if args.react_native else None,
    )


if __name__ == "__main__":
    main()
