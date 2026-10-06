from pathlib import Path
import modal

SHARED_DIR = Path(__file__).resolve().parent
LOCAL_STARTUP_SCRIPT = SHARED_DIR / "startup.sh"
REMOTE_STARTUP_SCRIPT = "/root/startup.sh"
LOCAL_GIT_BASH = Path(__file__).resolve().parent.parent / "git.bash"
REMOTE_GIT_BASH = "/root/.git.bash"
LOCAL_OPENCODE_CONFIG = SHARED_DIR / "opencode.json"
REMOTE_OPENCODE_CONFIG = "/root/.config/opencode/opencode.json"
LOCAL_ANTIGRAVITY_SETTINGS = SHARED_DIR / "antigravity-settings.json"
REMOTE_ANTIGRAVITY_SETTINGS = "/root/.gemini/antigravity-cli/settings.json"
LOCAL_ANTIGRAVITY_KEYBINDINGS = SHARED_DIR / "antigravity-keybindings.json"
REMOTE_ANTIGRAVITY_KEYBINDINGS = "/root/.gemini/antigravity-cli/keybindings.json"
SHARED_SSH_PUB_KEY = SHARED_DIR / "ssh-key.pub"
LOCAL_CLOUDFLARE_SECRET = Path(__file__).resolve().parent.parent / "secrets" / "cloudflare.env"
REMOTE_CLOUDFLARE_SECRET = "/root/secrets/cloudflare.env"
REMOTE_FETCH_SECRET = "/root/secrets/fetch.env"
SHARED_SECRET_NAME = "share0"

GRADLE_CACHE_PATH = "/root/.gradle/caches"
GRADLE_WRAPPER_PATH = "/root/.gradle/wrapper"


def get_gradle_volumes() -> dict[str, modal.Volume]:
    """Returns the Gradle cache and wrapper volume mounts for React Native."""
    return {
        GRADLE_CACHE_PATH: modal.Volume.from_name(
            "gradle-caches", create_if_missing=True
        ),
        GRADLE_WRAPPER_PATH: modal.Volume.from_name(
            "gradle-wrapper", create_if_missing=True
        ),
    }


# Shared Base Image: Cached once by Modal and shared between Standard and VM Sandboxes
base_image = (
    modal.Image.from_registry("ubuntu:24.04")
    .env({"DEBIAN_FRONTEND": "noninteractive"})
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
        # Install Node.js 24 and pnpm at image build time
        "curl -fsSL https://deb.nodesource.com/setup_24.x | bash -",
        "apt-get install -y nodejs",
        "corepack enable pnpm",
        "corepack prepare pnpm@10.31.0 --activate",
        # Install SOPS
        "curl -fsSL https://github.com/getsops/sops/releases/download/v3.13.3/sops-v3.13.3.linux.amd64 -o /usr/local/bin/sops",
        "chmod +x /usr/local/bin/sops",
        # Install Cloudflared
        "curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared",
        "chmod +x /usr/local/bin/cloudflared",
        # Configure SSH daemon
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

if LOCAL_CLOUDFLARE_SECRET.exists():
    base_image = base_image.add_local_file(
        LOCAL_CLOUDFLARE_SECRET, REMOTE_CLOUDFLARE_SECRET, copy=True
    )


def load_ssh_pub_key() -> str:
    """Loads SSH public key content from shared/ssh-key.pub.

    Raises FileNotFoundError if the shared public key is missing.
    """
    if not SHARED_SSH_PUB_KEY.exists():
        raise FileNotFoundError(
            f"SSH public key not found at {SHARED_SSH_PUB_KEY}."
        )
    return SHARED_SSH_PUB_KEY.read_text().strip()


def browser_enabled(
    *, browser: bool = False, opencode: bool = False, agy: bool = False
) -> bool:
    """Resolves whether Browser Tooling should be provisioned.

    A standalone `--browser` launch is supported, but any agent surface that can
    drive a browser implies it: `--opencode` and `--agy` enable it so their
    browser MCP servers work out of the box.
    """
    return browser or opencode or agy


def build_sandbox_image(
    *,
    opencode: bool = False,
    agy: bool = False,
    browser: bool = False,
    modal_tooling: bool = False,
    react_native: bool = False,
) -> modal.Image:
    """Constructs the layered Modal image according to requested features."""
    image = base_image
    path_prefixes: list[str] = []

    if opencode:
        image = image.run_commands("curl -fsSL https://opencode.ai/v2/install | bash")
        path_prefixes.append("/root/.opencode/bin")
        if LOCAL_OPENCODE_CONFIG.exists():
            image = image.add_local_file(
                LOCAL_OPENCODE_CONFIG, REMOTE_OPENCODE_CONFIG, copy=True
            )

    if agy:
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

    if browser:
        # Single shared Google Chrome used by both the Playwright and Chrome
        # DevTools MCP servers. Playwright installs it at
        # /opt/google/chrome/chrome -- the "chrome"/"stable" channel both MCP
        # servers resolve to by default -- and pulls the OS libraries it needs.
        image = image.run_commands("npx -y playwright install --with-deps chrome")

    if react_native:
        image = (
            image.apt_install("openjdk-17-jdk-headless")
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

    if modal_tooling:
        image = image.apt_install(
            "python3", "python3-pip", "python3-venv", "python-is-python3"
        ).run_commands(
            "mkdir -p /etc",
            "printf '[global]\\nbreak-system-packages = true\\n' > /etc/pip.conf",
        )

    if path_prefixes:
        image = image.env({"PATH": ":".join(path_prefixes) + ":${PATH}"})

    return image
