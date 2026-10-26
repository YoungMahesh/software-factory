from collections.abc import Iterable
from pathlib import Path
import modal

SHARED_DIR = Path(__file__).resolve().parent
LOCAL_STARTUP_SCRIPT = SHARED_DIR / "startup.sh"
REMOTE_STARTUP_SCRIPT = "/root/startup.sh"
LOCAL_ALIASES_BASH = SHARED_DIR / "aliases.bash"
REMOTE_ALIASES_BASH = "/root/.bash_aliases"
LOCAL_GITCONFIG = SHARED_DIR / "gitconfig"
REMOTE_GITCONFIG = "/root/.gitconfig"
LOCAL_GITCONFIG_MAHESH471978 = SHARED_DIR / "gitconfig-mahesh471978"
REMOTE_GITCONFIG_MAHESH471978 = "/root/.gitconfig-mahesh471978"
LOCAL_OPENCODE_CONFIG = SHARED_DIR / "opencode.json"
REMOTE_OPENCODE_CONFIG = "/root/.config/opencode/opencode.json"
LOCAL_ANTIGRAVITY_SETTINGS = SHARED_DIR / "antigravity-settings.json"
REMOTE_ANTIGRAVITY_SETTINGS = "/root/.gemini/antigravity-cli/settings.json"
LOCAL_ANTIGRAVITY_KEYBINDINGS = SHARED_DIR / "antigravity-keybindings.json"
REMOTE_ANTIGRAVITY_KEYBINDINGS = "/root/.gemini/antigravity-cli/keybindings.json"
LOCAL_ANTIGRAVITY_ONBOARDING = SHARED_DIR / "antigravity-onboarding.json"
REMOTE_ANTIGRAVITY_ONBOARDING = "/root/.gemini/antigravity-cli/cache/onboarding.json"
SHARED_SSH_PUB_KEY = SHARED_DIR / "ssh-key.pub"
LOCAL_SETUP_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "setup.sh"
REMOTE_SETUP_SCRIPT = "/root/scripts/setup.sh"
LOCAL_OPENCODE_SECRET = Path(__file__).resolve().parent.parent / "secrets" / "opencode.env"
REMOTE_OPENCODE_SECRET = "/root/secrets/opencode.env"
LOCAL_PI_SETTINGS = SHARED_DIR / "pi-settings.json"
REMOTE_PI_SETTINGS = "/root/.pi/agent/settings.json"
LOCAL_PI_MODELS = SHARED_DIR / "pi-models.json"
REMOTE_PI_MODELS = "/root/.pi/agent/models.json"
LOCAL_ANTIGRAVITY_SECRET = (
    Path(__file__).resolve().parent.parent / "secrets" / "antigravity-oauth-token.json"
)
REMOTE_ANTIGRAVITY_SECRET = "/root/secrets/antigravity-oauth-token.json"
LOCAL_MODAL_SECRET = Path(__file__).resolve().parent.parent / "secrets" / "modal.toml"
REMOTE_MODAL_SECRET = "/root/secrets/modal.toml"
LOCAL_CLOUDFLARE_SECRET = Path(__file__).resolve().parent.parent / "secrets" / "cloudflare.env"
REMOTE_CLOUDFLARE_SECRET = "/root/secrets/cloudflare.env"
REMOTE_FETCH_SECRET = "/root/secrets/fetch.env"
REMOTE_REPO_SECRETS_DIR = "/root/secrets/repo"
REMOTE_ORG_SECRETS_DIR = "/root/secrets/org"
REMOTE_ORG_TOKEN = "/root/secrets/org/token"
SHARED_SECRET_NAME = "share0"

LOCAL_FACTORY_ENTRYPOINT = SHARED_DIR / "factory_entrypoint.sh"
REMOTE_FACTORY_ENTRYPOINT = "/root/factory_entrypoint.sh"

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


def add_local_files_if_present(
    image: modal.Image, files: Iterable[tuple[Path | str, str]]
) -> modal.Image:
    """Conditionally stages existing local files into a Modal image."""
    for local_path, remote_path in files:
        if Path(local_path).exists():
            image = image.add_local_file(local_path, remote_path, copy=True)
    return image


BASE_IMAGE_FILES: list[tuple[Path, str]] = [
    (LOCAL_STARTUP_SCRIPT, REMOTE_STARTUP_SCRIPT),
    (LOCAL_ALIASES_BASH, REMOTE_ALIASES_BASH),
    (LOCAL_GITCONFIG, REMOTE_GITCONFIG),
    (LOCAL_GITCONFIG_MAHESH471978, REMOTE_GITCONFIG_MAHESH471978),
    (LOCAL_SETUP_SCRIPT, REMOTE_SETUP_SCRIPT),
    (LOCAL_CLOUDFLARE_SECRET, REMOTE_CLOUDFLARE_SECRET),
]


# Shared Base Image: Cached once by Modal and shared between Standard and VM Sandboxes
base_image = (
    modal.Image.from_registry("ubuntu:24.04")
    .env({"DEBIAN_FRONTEND": "noninteractive"})
    .apt_install(
        "curl",
        "git",
        "htop",
        "jq",
        "openssh-server",
        "wget",
        "docker.io",
        "docker-buildx",
        "docker-compose-v2",
        "unzip",
        "ripgrep",
        "age",
        "tree",
        "lsof",
        "psmisc",
        "fd-find",
        "python3",
        "python3-pip",
        "python3-venv",
        "python-is-python3",
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
        # Install Astral uv and uvx
        "curl -fsSL https://astral.sh/uv/install.sh | env UV_INSTALL_DIR='/usr/local/bin' sh",
        # Symlink fd-find to fd
        "ln -sf /usr/bin/fdfind /usr/local/bin/fd",
        # Configure global pip defaults to allow non-venv installs when needed
        "mkdir -p /etc && printf '[global]\\nbreak-system-packages = true\\n' > /etc/pip.conf",
        # Configure SSH daemon
        "mkdir -p /run/sshd /root/.ssh /etc/ssh/sshd_config.d",
        "echo 'PermitRootLogin prohibit-password' > /etc/ssh/sshd_config.d/modal.conf",
        "echo 'PubkeyAuthentication yes' >> /etc/ssh/sshd_config.d/modal.conf",
        "echo 'PasswordAuthentication no' >> /etc/ssh/sshd_config.d/modal.conf",
        "ssh-keygen -A",
    )
)

base_image = add_local_files_if_present(base_image, BASE_IMAGE_FILES)


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


T3_VERSION = "0.0.45"
T3_TAR_URL = f"https://github.com/pingdotgg/t3code/releases/download/v{T3_VERSION}/t3-{T3_VERSION}-linux-x64.tar.gz"


def build_sandbox_image(
    *,
    opencode: bool = False,
    agy: bool = False,
    browser: bool = False,
    modal_tooling: bool = False,
    react_native: bool = False,
    t3: bool = False,
    herdr: bool = False,
    pi: bool = False,
) -> modal.Image:
    """Constructs the layered Modal image according to requested features."""
    image = base_image
    path_prefixes: list[str] = []

    if opencode:
        image = image.run_commands("curl -fsSL https://opencode.ai/v2/install | bash")
        path_prefixes.append("/root/.opencode/bin")
        image = add_local_files_if_present(
            image,
            [
                (LOCAL_OPENCODE_CONFIG, REMOTE_OPENCODE_CONFIG),
                (LOCAL_OPENCODE_SECRET, REMOTE_OPENCODE_SECRET),
            ],
        )

    if agy:
        image = image.run_commands(
            "curl -fsSL https://antigravity.google/cli/install.sh | bash",
            "mkdir -p /root/.gemini/antigravity-cli /root/.gemini/antigravity-cli/cache",
        )
        path_prefixes.append("/root/.local/bin")
        image = add_local_files_if_present(
            image,
            [
                (LOCAL_ANTIGRAVITY_SETTINGS, REMOTE_ANTIGRAVITY_SETTINGS),
                (LOCAL_ANTIGRAVITY_KEYBINDINGS, REMOTE_ANTIGRAVITY_KEYBINDINGS),
                (LOCAL_ANTIGRAVITY_ONBOARDING, REMOTE_ANTIGRAVITY_ONBOARDING),
                (LOCAL_ANTIGRAVITY_SECRET, REMOTE_ANTIGRAVITY_SECRET),
            ],
        )

    if browser:
        # Single shared Google Chrome used by both the Playwright and Chrome
        # DevTools MCP servers. Playwright installs it at
        # /opt/google/chrome/chrome -- the "chrome"/"stable" channel both MCP
        # servers resolve to by default -- and pulls the OS libraries it needs.
        image = image.run_commands("npx -y playwright install --with-deps chrome")

    if react_native:
        image = (
            image.apt_install("openjdk-17-jdk-headless", "watchman")
            .env(
                {
                    "ANDROID_HOME": "/opt/android-sdk",
                    "ANDROID_SDK_ROOT": "/opt/android-sdk",
                    "JAVA_HOME": "/usr/lib/jvm/java-17-openjdk-amd64",
                }
            )
            .run_commands(
                "npm install --global @expo/ngrok@^4.1.0",
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
        image = add_local_files_if_present(
            image,
            [
                (LOCAL_MODAL_SECRET, REMOTE_MODAL_SECRET),
            ],
        )

    if t3:
        image = image.run_commands(
            "mkdir -p /opt/t3",
            f"curl -fsSL {T3_TAR_URL} | tar -xz -C /opt/t3 --strip-components=1",
            "ln -sf /opt/t3/t3 /usr/local/bin/t3",
        )

    if herdr:
        image = image.run_commands(
            "curl -fsSL https://herdr.dev/install.sh | env HERDR_INSTALL_DIR=/usr/local/bin sh"
        )

    if pi:
        image = image.run_commands(
            "npm install -g --ignore-scripts @earendil-works/pi-coding-agent"
        )
        image = add_local_files_if_present(
            image,
            [
                (LOCAL_PI_SETTINGS, REMOTE_PI_SETTINGS),
                (LOCAL_PI_MODELS, REMOTE_PI_MODELS),
                (LOCAL_OPENCODE_SECRET, REMOTE_OPENCODE_SECRET),
            ],
        )

    if path_prefixes:
        image = image.env({"PATH": ":".join(path_prefixes) + ":${PATH}"})

    return image
