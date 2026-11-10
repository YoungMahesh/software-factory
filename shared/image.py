from collections.abc import Iterable
from pathlib import Path
import modal

from shared.t3_patches import (
    T3_CURRENT_MODELS_PATCH_REPLACEMENT,
    T3_CURRENT_MODELS_PATCH_TARGET,
    T3_DRIVER_ORDER_PATCH_REPLACEMENT,
    T3_DRIVER_ORDER_PATCH_TARGET,
    T3_IPV6_PATCH_REPLACEMENT,
    T3_IPV6_PATCH_TARGET,
    T3_MODELS_MANIFEST_PATCH_REPLACEMENT,
    T3_MODELS_MANIFEST_PATCH_TARGET,
    T3_PATCH_SCRIPT,
    T3_SSH_PATCH_REPLACEMENT,
    T3_SSH_PATCH_TARGET,
)

SHARED_DIR = Path(__file__).resolve().parent
LOCAL_STARTUP_SCRIPT = SHARED_DIR / "startup.sh"
REMOTE_STARTUP_SCRIPT = "/root/startup.sh"
LOCAL_ALIASES_BASH = SHARED_DIR / "aliases.bash"
REMOTE_ALIASES_BASH = "/root/.bash_aliases"
LOCAL_GITCONFIG = SHARED_DIR / "gitconfig"
REMOTE_GITCONFIG = "/root/.gitconfig"
LOCAL_OPENCODE_CONFIG = SHARED_DIR / "opencode.json"
REMOTE_OPENCODE_CONFIG = "/root/.config/opencode/opencode.json"
LOCAL_ANTIGRAVITY_SETTINGS = SHARED_DIR / "antigravity-settings.json"
REMOTE_ANTIGRAVITY_SETTINGS = "/root/.gemini/antigravity-cli/settings.json"
LOCAL_ANTIGRAVITY_KEYBINDINGS = SHARED_DIR / "antigravity-keybindings.json"
REMOTE_ANTIGRAVITY_KEYBINDINGS = "/root/.gemini/antigravity-cli/keybindings.json"
LOCAL_ANTIGRAVITY_ONBOARDING = SHARED_DIR / "antigravity-onboarding.json"
REMOTE_ANTIGRAVITY_ONBOARDING = "/root/.gemini/antigravity-cli/cache/onboarding.json"
SHARED_SSH_PUB_KEY = SHARED_DIR / "ssh-key.pub"

REPO_ROOT = Path(__file__).resolve().parent.parent


def _resolve_dir(*candidates: Path) -> Path:
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


def _resolve_file(filename: str, *candidate_dirs: Path) -> Path:
    for candidate_dir in candidate_dirs:
        candidate_file = candidate_dir / filename
        if candidate_file.is_file():
            return candidate_file
    return candidate_dirs[0] / filename


LOCAL_SCRIPTS_DIR = _resolve_dir(
    REPO_ROOT / "scripts",
    REPO_ROOT / ".scripts",
    Path("/root/.scripts"),
    Path("/root/scripts"),
)

_SCRIPTS_SEARCH_DIRS = (
    LOCAL_SCRIPTS_DIR,
    REPO_ROOT / "scripts",
    REPO_ROOT / ".scripts",
    Path("/root/.scripts"),
    Path("/root/scripts"),
)

LOCAL_SETUP_SCRIPT = _resolve_file("setup.sh", *_SCRIPTS_SEARCH_DIRS)
REMOTE_SETUP_SCRIPT = "/root/.scripts/setup.sh"
LOCAL_AGYQ = _resolve_file("agyq", *_SCRIPTS_SEARCH_DIRS)
REMOTE_AGYQ = "/usr/local/bin/agyq"
LOCAL_GHLS = _resolve_file("ghls", *_SCRIPTS_SEARCH_DIRS)
REMOTE_GHLS = "/usr/local/bin/ghls"
LOCAL_GHPR = _resolve_file("ghpr", *_SCRIPTS_SEARCH_DIRS)
REMOTE_GHPR = "/usr/local/bin/ghpr"
LOCAL_GHCLONE = _resolve_file("ghclone", *_SCRIPTS_SEARCH_DIRS)
REMOTE_GHCLONE = "/usr/local/bin/ghclone"
LOCAL_AGYPROFILE = _resolve_file("agyprofile", *_SCRIPTS_SEARCH_DIRS)
REMOTE_AGYPROFILE = "/usr/local/bin/agyprofile"
LOCAL_DECRYPT_REPO_ENV = _resolve_file("decrypt_repo_env.py", *_SCRIPTS_SEARCH_DIRS)
REMOTE_DECRYPT_REPO_ENV = "/usr/local/bin/decrypt-repo-env"
LOCAL_ENCRYPT_REPO_ENV = _resolve_file("encrypt_repo_env.py", *_SCRIPTS_SEARCH_DIRS)
REMOTE_ENCRYPT_REPO_ENV = "/usr/local/bin/encrypt-repo-env"

LOCAL_PI_SETTINGS = SHARED_DIR / "pi-settings.json"
REMOTE_PI_SETTINGS = "/root/.pi/agent/settings.json"
LOCAL_PI_MODELS = SHARED_DIR / "pi-models.json"
REMOTE_PI_MODELS = "/root/.pi/agent/models.json"
LOCAL_T3_KEYBINDINGS = SHARED_DIR / "t3-keybindings.json"
REMOTE_T3_KEYBINDINGS = "/root/.t3/userdata/keybindings.json"
LOCAL_T3_WRAPPER = SHARED_DIR / "t3-wrapper.sh"
REMOTE_T3_WRAPPER = "/usr/local/bin/t3"
LOCAL_T3_USAGE_SYNC = SHARED_DIR / "t3_usage_sync.py"
REMOTE_T3_USAGE_SYNC = "/usr/local/bin/t3-usage-sync"

GRADLE_CACHE_PATH = "/root/.gradle/caches"
GRADLE_WRAPPER_PATH = "/root/.gradle/wrapper"

T3_USAGE_VOLUME_NAME = "t3code-usage-v1"
T3_STORAGE_MOUNT_PATH = "/root/.t3-storage"
DEFAULT_T3_USAGE_VOLUME = T3_USAGE_VOLUME_NAME


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


def get_t3_usage_volume(name: str = T3_USAGE_VOLUME_NAME) -> modal.Volume:
    """Returns the persistent volume for T3 Code usage and transcripts."""
    return modal.Volume.from_name(name, create_if_missing=True)


def get_t3_usage_volumes(name: str = T3_USAGE_VOLUME_NAME) -> dict[str, modal.Volume]:
    """Returns the volume mount mapping for T3 Code usage persistence."""
    return {T3_STORAGE_MOUNT_PATH: get_t3_usage_volume(name)}


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
    (LOCAL_SETUP_SCRIPT, REMOTE_SETUP_SCRIPT),
    (LOCAL_AGYQ, REMOTE_AGYQ),
    (LOCAL_GHLS, REMOTE_GHLS),
    (LOCAL_GHPR, REMOTE_GHPR),
    (LOCAL_GHCLONE, REMOTE_GHCLONE),
    (LOCAL_AGYPROFILE, REMOTE_AGYPROFILE),
    (LOCAL_DECRYPT_REPO_ENV, REMOTE_DECRYPT_REPO_ENV),
    (LOCAL_ENCRYPT_REPO_ENV, REMOTE_ENCRYPT_REPO_ENV),
    (LOCAL_T3_USAGE_SYNC, REMOTE_T3_USAGE_SYNC),
]


# Shared Base Image: Cached once by Modal and shared between Standard and VM Sandboxes
base_image = (
    modal.Image.from_registry("ubuntu:24.04", add_python="3.12")
    .env({"DEBIAN_FRONTEND": "noninteractive"})
    .apt_install(
        "curl",
        "git",
        "gh",
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
base_image = base_image.run_commands(
    "chmod +x /usr/local/bin/agyq /usr/local/bin/ghls /usr/local/bin/ghpr /usr/local/bin/ghclone /usr/local/bin/agyprofile /usr/local/bin/decrypt-repo-env /usr/local/bin/encrypt-repo-env /usr/local/bin/t3-usage-sync /root/.scripts/setup.sh 2>/dev/null || true",
    "ln -sf /usr/local/bin/agyprofile /usr/local/bin/switch-agy-profile 2>/dev/null || true",
    "ln -sf /usr/local/bin/agyprofile /usr/local/bin/switch-agy-profile.sh 2>/dev/null || true",
    "ln -sf /usr/local/bin/decrypt-repo-env /usr/local/bin/decrypt_repo_env.py 2>/dev/null || true",
    "ln -sf /usr/local/bin/encrypt-repo-env /usr/local/bin/encrypt_repo_env.py 2>/dev/null || true",
    "ln -sf /usr/local/bin/t3-usage-sync /usr/local/bin/t3_usage_sync 2>/dev/null || true",
    "mkdir -p /root/.scripts",
    "ln -sf /usr/local/bin/agyq /root/.scripts/agyq 2>/dev/null || true",
    "ln -sf /usr/local/bin/ghls /root/.scripts/ghls 2>/dev/null || true",
    "ln -sf /usr/local/bin/ghpr /root/.scripts/ghpr 2>/dev/null || true",
    "ln -sf /usr/local/bin/ghclone /root/.scripts/ghclone 2>/dev/null || true",
    "ln -sf /usr/local/bin/agyprofile /root/.scripts/agyprofile 2>/dev/null || true",
    "ln -sf /usr/local/bin/agyprofile /root/.scripts/switch-agy-profile 2>/dev/null || true",
    "ln -sf /usr/local/bin/agyprofile /root/.scripts/switch-agy-profile.sh 2>/dev/null || true",
    "ln -sf /usr/local/bin/decrypt-repo-env /root/.scripts/decrypt-repo-env 2>/dev/null || true",
    "ln -sf /usr/local/bin/encrypt-repo-env /root/.scripts/encrypt-repo-env 2>/dev/null || true",
    "ln -sf /usr/local/bin/t3-usage-sync /root/.scripts/t3-usage-sync 2>/dev/null || true",
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


# T3 Code release configuration and binary patch target
T3_VERSION = "0.1.3"
T3_TAR_URL = f"https://github.com/pingdotgg/t3code/releases/download/v{T3_VERSION}/t3-{T3_VERSION}-linux-x64.tar.gz"

# Antigravity ACP plugin bundle configuration
T3_ANTIGRAVITY_VERSION = "1.3.0"
T3_ANTIGRAVITY_RELEASE_ID = (
    "9fb60956af0a9d76220a4db91ca9ac88e2a2372ad68f985ab5fceace6b825b96"
)
T3_ANTIGRAVITY_URL = (
    f"https://dl.google.com/agy-extensions/releases/linux/"
    f"agy-acp-server-{T3_ANTIGRAVITY_VERSION}-linux-x86_64.zip"
)
T3_ANTIGRAVITY_MANAGED_DIR = "/root/.t3/tools/antigravity-acp/linux-x64"
T3_ANTIGRAVITY_VERSION_DIR = (
    f"{T3_ANTIGRAVITY_MANAGED_DIR}/versions/{T3_ANTIGRAVITY_RELEASE_ID}"
)
T3_INSTALL_COMPLETE_JSON = (
    f'{{"releaseId":"{T3_ANTIGRAVITY_RELEASE_ID}","version":"{T3_ANTIGRAVITY_VERSION}",'
    f'"executable":{{"name":"agy_acp_server.par","bytes":926533965}},'
    f'"harness":{{"name":"localharness_external","bytes":130388040}}}}'
)
T3_ACTIVE_JSON = f'{{"releaseId":"{T3_ANTIGRAVITY_RELEASE_ID}"}}'


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
    """Builds a customized sandbox image layered on top of base_image."""
    image = base_image
    path_prefixes: list[str] = []

    if react_native:
        image = (
            image.env(
                {
                    "DEBIAN_FRONTEND": "noninteractive",
                    "ANDROID_HOME": "/opt/android-sdk",
                    "ANDROID_SDK_ROOT": "/opt/android-sdk",
                    "JAVA_HOME": "/usr/lib/jvm/java-17-openjdk-amd64",
                }
            )
            .apt_install(
                "openjdk-17-jdk",
                "watchman",
            )
            .run_commands(
                "npm install -g --ignore-scripts @expo/ngrok",
                "mkdir -p /opt/android-sdk/cmdline-tools",
                (
                    "curl -fsSL https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip "
                    "-o /tmp/cmdline-tools.zip"
                ),
                "unzip -q /tmp/cmdline-tools.zip -d /opt/android-sdk/cmdline-tools",
                "mv /opt/android-sdk/cmdline-tools/cmdline-tools /opt/android-sdk/cmdline-tools/latest",
                "rm -f /tmp/cmdline-tools.zip",
                (
                    "yes | /opt/android-sdk/cmdline-tools/latest/bin/sdkmanager --licenses > /dev/null || true"
                ),
                (
                    "/opt/android-sdk/cmdline-tools/latest/bin/sdkmanager "
                    "'platform-tools' 'platforms;android-34' 'build-tools;34.0.0' 'cmake;3.22.1' 'ndk;26.1.10909125'"
                ),
                "mkdir -p /root/.gradle /run/user/0",
            )
        )
        path_prefixes.extend(
            [
                "/opt/android-sdk/cmdline-tools/latest/bin",
                "/opt/android-sdk/platform-tools",
            ]
        )

    if opencode or t3:
        image = image.run_commands(
            "curl -fsSL https://opencode.ai/v2/install | bash"
        )
        path_prefixes.append("/root/.opencode/bin")
        image = add_local_files_if_present(
            image,
            [
                (LOCAL_OPENCODE_CONFIG, REMOTE_OPENCODE_CONFIG),
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
            ],
        )

    if browser_enabled(browser=browser, opencode=opencode, agy=agy):
        image = image.run_commands(
            "uvx playwright install --with-deps chromium",
            "chmod -R 777 /root/.cache/ms-playwright 2>/dev/null || true",
        )

    if modal_tooling:
        image = image.run_commands(
            "python3 -m venv /opt/modal-env",
            "/opt/modal-env/bin/pip install --upgrade modal",
            "mkdir -p /root/.modal",
        )
        path_prefixes.append("/opt/modal-env/bin")

    if t3:
        image = image.run_commands(
            "mkdir -p /opt/t3",
            f"curl -fsSL {T3_TAR_URL} | tar -xz -C /opt/t3 --strip-components=1",
            "ln -sf /opt/t3/t3 /usr/local/bin/t3",
            T3_PATCH_SCRIPT,
            f"mkdir -p {T3_ANTIGRAVITY_VERSION_DIR}",
            f"curl -fsSL {T3_ANTIGRAVITY_URL} -o /tmp/agy-acp.zip",
            f"unzip -q /tmp/agy-acp.zip -d {T3_ANTIGRAVITY_VERSION_DIR}",
            "rm -f /tmp/agy-acp.zip",
            (
                f"chmod 0755 {T3_ANTIGRAVITY_VERSION_DIR}/agy_acp_server.par "
                f"{T3_ANTIGRAVITY_VERSION_DIR}/localharness_external"
            ),
            f"echo '{T3_INSTALL_COMPLETE_JSON}' > {T3_ANTIGRAVITY_VERSION_DIR}/.install-complete.json",
            f"echo '{T3_ACTIVE_JSON}' > {T3_ANTIGRAVITY_MANAGED_DIR}/active.json",
        )
        image = add_local_files_if_present(
            image,
            [
                (LOCAL_T3_KEYBINDINGS, REMOTE_T3_KEYBINDINGS),
                (LOCAL_T3_WRAPPER, REMOTE_T3_WRAPPER),
            ],
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
            ],
        )

    if path_prefixes:
        image = image.env({"PATH": ":".join(path_prefixes) + ":${PATH}"})

    return image
