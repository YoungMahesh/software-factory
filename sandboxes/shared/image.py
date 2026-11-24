from collections.abc import Iterable
from pathlib import Path
import modal

from shared.t3_patches import (
    T3_DRIVER_ORDER_PATCH_REPLACEMENT,
    T3_DRIVER_ORDER_PATCH_TARGET,
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
SHARED_SSH_PUB_KEY = SHARED_DIR / "ssh-key.pub"
LOCAL_DESKTOP_SERVICE = SHARED_DIR / "desktop-service"
REMOTE_DESKTOP_SERVICE = "/usr/local/bin/desktop-service"

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
LOCAL_PUSH_REPO_ENV = _resolve_file("push_repo_env.py", *_SCRIPTS_SEARCH_DIRS)
REMOTE_PUSH_REPO_ENV = "/usr/local/bin/push-repo-env"
LOCAL_PULL_REPO_ENV = _resolve_file("pull_repo_env.py", *_SCRIPTS_SEARCH_DIRS)
REMOTE_PULL_REPO_ENV = "/usr/local/bin/pull-repo-env"
LOCAL_CREATE_DB = _resolve_file("create_db.py", *_SCRIPTS_SEARCH_DIRS)
REMOTE_CREATE_DB = "/usr/local/bin/create-db"
LOCAL_CREATE_S3 = _resolve_file("create_s3.py", *_SCRIPTS_SEARCH_DIRS)
REMOTE_CREATE_S3 = "/usr/local/bin/create-s3"
LOCAL_POST_CHECKOUT_HOOK = SHARED_DIR / "git-hooks" / "post-checkout"
REMOTE_POST_CHECKOUT_HOOK = "/root/.git-hooks/post-checkout"

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

SOPS_VERSION = "v3.13.3"
SOPS_INSTALL_COMMANDS = (
    f"curl -fsSL https://github.com/getsops/sops/releases/download/{SOPS_VERSION}/sops-{SOPS_VERSION}.linux.amd64 -o /usr/local/bin/sops",
    "chmod +x /usr/local/bin/sops",
)


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


BASE_IMAGE_FILES: list[tuple[Path, str]] = [\
    (LOCAL_STARTUP_SCRIPT, REMOTE_STARTUP_SCRIPT),
    (LOCAL_ALIASES_BASH, REMOTE_ALIASES_BASH),
    (LOCAL_GITCONFIG, REMOTE_GITCONFIG),
    (LOCAL_SETUP_SCRIPT, REMOTE_SETUP_SCRIPT),
    (LOCAL_AGYQ, REMOTE_AGYQ),
    (LOCAL_GHLS, REMOTE_GHLS),
    (LOCAL_GHPR, REMOTE_GHPR),
    (LOCAL_GHCLONE, REMOTE_GHCLONE),
    (LOCAL_AGYPROFILE, REMOTE_AGYPROFILE),
    (LOCAL_PUSH_REPO_ENV, REMOTE_PUSH_REPO_ENV),
    (LOCAL_PULL_REPO_ENV, REMOTE_PULL_REPO_ENV),
    (LOCAL_CREATE_DB, REMOTE_CREATE_DB),
    (LOCAL_CREATE_S3, REMOTE_CREATE_S3),
    (LOCAL_T3_USAGE_SYNC, REMOTE_T3_USAGE_SYNC),
    (LOCAL_POST_CHECKOUT_HOOK, REMOTE_POST_CHECKOUT_HOOK),
    (LOCAL_DESKTOP_SERVICE, REMOTE_DESKTOP_SERVICE),
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
        # System libraries and fonts required by headless Chromium/Chrome and T3 Code browser
        "libnss3",
        "libatk1.0-0t64",
        "libatk-bridge2.0-0t64",
        "libatspi2.0-0t64",
        "libdbus-1-3",
        "libx11-6",
        "libxcb1",
        "libxcomposite1",
        "libxdamage1",
        "libxext6",
        "libxfixes3",
        "libxrandr2",
        "libxkbcommon0",
        "libgbm1",
        "libasound2t64",
        "libexpat1",
        "fontconfig",
        "fonts-liberation",
    )
    .run_commands(
        # Install Node.js 24 and pnpm at image build time
        "curl -fsSL https://deb.nodesource.com/setup_24.x | bash -",
        "apt-get install -y nodejs",
        "corepack enable pnpm",
        "corepack prepare pnpm@10.31.0 --activate",
        # Install SOPS
        *SOPS_INSTALL_COMMANDS,
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
    "chmod +x /usr/local/bin/agyq /usr/local/bin/ghls /usr/local/bin/ghpr /usr/local/bin/ghclone /usr/local/bin/agyprofile /usr/local/bin/push-repo-env /usr/local/bin/pull-repo-env /usr/local/bin/create-db /usr/local/bin/create-s3 /usr/local/bin/t3-usage-sync /usr/local/bin/desktop-service /root/.scripts/setup.sh 2>/dev/null || true",
    "ln -sf /usr/local/bin/agyprofile /usr/local/bin/switch-agy-profile 2>/dev/null || true",
    "ln -sf /usr/local/bin/agyprofile /usr/local/bin/switch-agy-profile.sh 2>/dev/null || true",
    "ln -sf /usr/local/bin/push-repo-env /usr/local/bin/push_repo_env.py 2>/dev/null || true",
    "ln -sf /usr/local/bin/pull-repo-env /usr/local/bin/pull_repo_env.py 2>/dev/null || true",
    "ln -sf /usr/local/bin/create-db /usr/local/bin/create_db.py 2>/dev/null || true",
    "ln -sf /usr/local/bin/create-s3 /usr/local/bin/create_s3.py 2>/dev/null || true",
    "ln -sf /usr/local/bin/t3-usage-sync /usr/local/bin/t3_usage_sync 2>/dev/null || true",
    "mkdir -p /root/.scripts",
    "ln -sf /usr/local/bin/agyq /root/.scripts/agyq 2>/dev/null || true",
    "ln -sf /usr/local/bin/ghls /root/.scripts/ghls 2>/dev/null || true",
    "ln -sf /usr/local/bin/ghpr /root/.scripts/ghpr 2>/dev/null || true",
    "ln -sf /usr/local/bin/ghclone /root/.scripts/ghclone 2>/dev/null || true",
    "ln -sf /usr/local/bin/agyprofile /root/.scripts/agyprofile 2>/dev/null || true",
    "ln -sf /usr/local/bin/agyprofile /root/.scripts/switch-agy-profile 2>/dev/null || true",
    "ln -sf /usr/local/bin/agyprofile /root/.scripts/switch-agy-profile.sh 2>/dev/null || true",
    "ln -sf /usr/local/bin/push-repo-env /root/.scripts/push-repo-env 2>/dev/null || true",
    "ln -sf /usr/local/bin/pull-repo-env /root/.scripts/pull-repo-env 2>/dev/null || true",
    "ln -sf /usr/local/bin/create-db /root/.scripts/create-db 2>/dev/null || true",
    "ln -sf /usr/local/bin/create-s3 /root/.scripts/create-s3 2>/dev/null || true",
    "ln -sf /usr/local/bin/t3-usage-sync /root/.scripts/t3-usage-sync 2>/dev/null || true",
    "chmod +x /root/.git-hooks/post-checkout 2>/dev/null || true",
)
base_image = base_image.add_local_dir(
    SHARED_DIR / "skills", "/root/.agents/skills", copy=True
).run_commands(
    "mkdir -p /root/.gemini/config",
    "ln -s /root/.agents/skills /root/.gemini/config/skills",
)


def load_ssh_pub_key() -> str:
    """Loads SSH public key content from shared/ssh-key.pub.

    Raises FileNotFoundError if the shared public key is missing."""
    if not SHARED_SSH_PUB_KEY.exists():
        raise FileNotFoundError(
            f"SSH public key not found at {SHARED_SSH_PUB_KEY}."
        )
    return SHARED_SSH_PUB_KEY.read_text().strip()


def browser_enabled(
    *,
    browser: bool = False,
    t3: bool = False,
) -> bool:
    """Resolves whether Browser Tooling should be provisioned.

    A standalone `--browser` launch is supported, but `--t3` implies it so
    browser MCP servers and built-in browser panels work out of the box."""
    return browser or t3


# T3 Code release configuration and binary patch target
T3_VERSION = "0.1.11"
CODEX_VERSION = "0.171.0"
LOCAL_CODEXPROFILE = _resolve_file("codexprofile", *_SCRIPTS_SEARCH_DIRS)
REMOTE_CODEXPROFILE = "/usr/local/bin/codexprofile"
T3_TAR_URL = f"https://github.com/pingdotgg/t3code/releases/download/v{T3_VERSION}/t3-{T3_VERSION}-linux-x64.tar.gz"

# Antigravity ACP runtime configuration
T3_ANTIGRAVITY_VERSION = "1.5.15"
T3_ANTIGRAVITY_SHA512 = (
    "af3f0be58b8475940d79f9abea19e762ecc3d265ea9f56cff8dd805e27ba299b"
    "44a305a79504a7ffe6ebdfa29a294c56edc4caed1875990bfaf2fef1508ec8b0"
)
T3_ANTIGRAVITY_RELEASE_ID = T3_ANTIGRAVITY_SHA512[:64]
T3_ANTIGRAVITY_URL = (
    f"https://storage.googleapis.com/antigravity-public/antigravity-cli/"
    f"{T3_ANTIGRAVITY_VERSION}-5514532022517760/linux-x64/cli_linux_x64.tar.gz"
)
T3_ANTIGRAVITY_MANAGED_DIR = "/root/.t3/tools/antigravity-acp/linux-x64"
T3_ANTIGRAVITY_VERSION_DIR = (
    f"{T3_ANTIGRAVITY_MANAGED_DIR}/versions/{T3_ANTIGRAVITY_RELEASE_ID}"
)
T3_ANTIGRAVITY_BYTES = 273879752
T3_INSTALL_COMPLETE_JSON = (
    f'{{"releaseId":"{T3_ANTIGRAVITY_RELEASE_ID}","version":"{T3_ANTIGRAVITY_VERSION}",'
    f'"executable":{{"name":"antigravity","bytes":{T3_ANTIGRAVITY_BYTES}}}}}'
)
T3_ACTIVE_JSON = f'{{"releaseId":"{T3_ANTIGRAVITY_RELEASE_ID}"}}'


def build_sandbox_image(
    *,
    browser: bool = False,
    modal_tooling: bool = False,
    react_native: bool = False,
    t3: bool = False,
    xfce: bool = False,
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

    if t3:
        image = image.run_commands(
            "curl -fsSL https://opencode.ai/v2/install | bash"
        )
        path_prefixes.append("/root/.opencode/bin")
        image = add_local_files_if_present(
            image,
            [
                (LOCAL_OPENCODE_CONFIG, REMOTE_OPENCODE_CONFIG),
                (LOCAL_CODEXPROFILE, REMOTE_CODEXPROFILE),
            ],
        )

    if browser_enabled(browser=browser, t3=t3):
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
            "chmod 755 /usr/local/bin/codexprofile",
            f"npm install -g @openai/codex@{CODEX_VERSION}",
            "mkdir -p /opt/t3",
            f"curl -fsSL {T3_TAR_URL} | tar -xz -C /opt/t3 --strip-components=1",
            "ln -sf /opt/t3/t3 /usr/local/bin/t3",
            T3_PATCH_SCRIPT,
            f"mkdir -p {T3_ANTIGRAVITY_VERSION_DIR}",
            f"curl -fsSL {T3_ANTIGRAVITY_URL} | tar -xz -C {T3_ANTIGRAVITY_VERSION_DIR}",
            f"chmod 0755 {T3_ANTIGRAVITY_VERSION_DIR}/antigravity",
            f"echo '{T3_INSTALL_COMPLETE_JSON}' > {T3_ANTIGRAVITY_VERSION_DIR}/.install-complete.json",
            f"echo '{T3_ACTIVE_JSON}' > {T3_ANTIGRAVITY_MANAGED_DIR}/active.json",
            "/opt/t3/t3 browser setup",
        )
        image = add_local_files_if_present(
            image,
            [
                (LOCAL_T3_KEYBINDINGS, REMOTE_T3_KEYBINDINGS),
                (LOCAL_T3_WRAPPER, REMOTE_T3_WRAPPER),
            ],
        )

    if xfce:
        image = (
            image.apt_install(
                "xfce4", "xfce4-terminal", "dbus-x11",
                "tigervnc-standalone-server", "tigervnc-tools",
                "novnc", "websockify", "xdotool", "scrot",
            )
            .run_commands(
                "wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb",
                "apt-get install -y /tmp/chrome.deb && rm -f /tmp/chrome.deb",
                "sed -i 's/CLEANUP => 1/CLEANUP => 0/' /usr/share/perl5/TigerVNC/Wrapper.pm 2>/dev/null || true",
                "sed -i 's|\"$HERE/chrome\"|\"$HERE/chrome\" --no-sandbox --disable-dev-shm-usage|' /opt/google/chrome/google-chrome 2>/dev/null || true",
                "sed -i 's|Exec=/usr/bin/google-chrome-stable|Exec=/usr/bin/google-chrome-stable --no-sandbox --disable-dev-shm-usage|' /usr/share/applications/google-chrome.desktop 2>/dev/null || true",
            )
        )

    if path_prefixes:
        image = image.env({"PATH": ":".join(path_prefixes) + ":${PATH}"})

    return image
