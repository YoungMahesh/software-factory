#!/usr/bin/env bash
set -euo pipefail

REF="${1:-main}"

# 0. Setup and start SSH server
mkdir -p /run/sshd /root/.ssh
ssh-keygen -A 2>/dev/null || true
if [ -n "${SSH_AUTHORIZED_KEY:-}" ]; then
    echo "$SSH_AUTHORIZED_KEY" > /root/.ssh/authorized_keys
fi
chmod 700 /root/.ssh
if [ -f /root/.ssh/authorized_keys ]; then
    chmod 600 /root/.ssh/authorized_keys
fi
/usr/sbin/sshd

# 1. Clone repository
if [ -z "${GH_REPO:-}" ]; then
    echo "ERROR: GH_REPO environment variable is not set." >&2
    exit 1
fi

REPO_NAME=$(basename "$GH_REPO")
TARGET_DIR="/root/$REPO_NAME"

git config --global advice.detachedHead false
git config --global user.name "Mahesh"
git config --global user.email "maheshghamand@gmail.com"
git config --global init.defaultBranch $REF

if [ ! -d "$TARGET_DIR" ]; then
    echo "🏝️  Cloning $GH_REPO (ref: $REF)..."
    GIT_ASKPASS=echo git clone --quiet --branch "$REF" --single-branch \
        "https://oauth2:${GH_TOKEN}@github.com/${GH_REPO}.git" "$TARGET_DIR"
fi

cd "$TARGET_DIR"
if [ -f /root/.git.bash ]; then
    grep -qxF "source /root/.git.bash" ~/.bashrc 2>/dev/null || echo "source /root/.git.bash" >> ~/.bashrc
fi
grep -qxF "cd $TARGET_DIR" ~/.bashrc 2>/dev/null || echo "cd $TARGET_DIR" >> ~/.bashrc
grep -qxF "export HOSTNAME=0.0.0.0" ~/.bashrc 2>/dev/null || echo "export HOSTNAME=0.0.0.0" >> ~/.bashrc
grep -qxF "export PORT=${PORT:-3000}" ~/.bashrc 2>/dev/null || echo "export PORT=${PORT:-3000}" >> ~/.bashrc
# sshd builds a clean environment for login sessions, so the image-level PATH alone
# does not reach interactive shells.
if [ "${ENABLE_OPENCODE:-}" = "1" ]; then
    grep -qxF 'export PATH="/root/.opencode/bin:$PATH"' ~/.bashrc 2>/dev/null || echo 'export PATH="/root/.opencode/bin:$PATH"' >> ~/.bashrc
fi
if [ "${ENABLE_ANTIGRAVITY:-}" = "1" ]; then
    grep -qxF 'export PATH="/root/.local/bin:$PATH"' ~/.bashrc 2>/dev/null || echo 'export PATH="/root/.local/bin:$PATH"' >> ~/.bashrc
fi
if [ "${ENABLE_REACT_NATIVE:-}" = "1" ]; then
    grep -qxF 'export ANDROID_HOME="/opt/android-sdk"' ~/.bashrc 2>/dev/null || echo 'export ANDROID_HOME="/opt/android-sdk"' >> ~/.bashrc
    grep -qxF 'export ANDROID_SDK_ROOT="/opt/android-sdk"' ~/.bashrc 2>/dev/null || echo 'export ANDROID_SDK_ROOT="/opt/android-sdk"' >> ~/.bashrc
    grep -qxF 'export JAVA_HOME="/usr/lib/jvm/java-17-openjdk-amd64"' ~/.bashrc 2>/dev/null || echo 'export JAVA_HOME="/usr/lib/jvm/java-17-openjdk-amd64"' >> ~/.bashrc
    grep -qxF 'export PATH="$PATH:/opt/android-sdk/cmdline-tools/latest/bin:/opt/android-sdk/platform-tools"' ~/.bashrc 2>/dev/null || echo 'export PATH="$PATH:/opt/android-sdk/cmdline-tools/latest/bin:/opt/android-sdk/platform-tools"' >> ~/.bashrc
    if [ -n "${METRO_PORT:-}" ]; then
        grep -qxF "export METRO_PORT=$METRO_PORT" ~/.bashrc 2>/dev/null || echo "export METRO_PORT=$METRO_PORT" >> ~/.bashrc
    fi

    # Also persist to /etc/environment for non-interactive / login session consistency
    grep -qxF 'ANDROID_HOME="/opt/android-sdk"' /etc/environment 2>/dev/null || echo 'ANDROID_HOME="/opt/android-sdk"' >> /etc/environment
    grep -qxF 'ANDROID_SDK_ROOT="/opt/android-sdk"' /etc/environment 2>/dev/null || echo 'ANDROID_SDK_ROOT="/opt/android-sdk"' >> /etc/environment
    grep -qxF 'JAVA_HOME="/usr/lib/jvm/java-17-openjdk-amd64"' /etc/environment 2>/dev/null || echo 'JAVA_HOME="/usr/lib/jvm/java-17-openjdk-amd64"' >> /etc/environment

    # Quick verification banner (near-instant filesystem checks, no JVM startup penalty)
    JAVA_VER=$(java -version 2>&1 | head -n 1 | cut -d'"' -f2 || echo "Not found")
    PLATFORMS=$(ls -1 /opt/android-sdk/platforms 2>/dev/null | tr '\n' ' ' || echo "None")
    BUILD_TOOLS=$(ls -1 /opt/android-sdk/build-tools 2>/dev/null | tr '\n' ' ' || echo "None")
    NDK_VER=$(ls -1 /opt/android-sdk/ndk 2>/dev/null | tr '\n' ' ' || echo "None")
    CMAKE_VER=$(ls -1 /opt/android-sdk/cmake 2>/dev/null | tr '\n' ' ' || echo "None")

    echo "📱 React Native Tooling Active:"
    echo "   • Java: OpenJDK $JAVA_VER"
    echo "   • Android SDK: /opt/android-sdk (Platforms: $PLATFORMS | Build-Tools: $BUILD_TOOLS)"
    echo "   • NDK: $NDK_VER | CMake: $CMAKE_VER"

    # Install on-demand inspection utility
    cat << 'EOF' > /usr/local/bin/check-react-native
#!/usr/bin/env bash
echo "=== Java ===" && java -version
echo "=== Android Tools ===" && adb --version && sdkmanager --version
echo "=== Environment Variables ===" && echo "JAVA_HOME: $JAVA_HOME" && echo "ANDROID_HOME: $ANDROID_HOME"
echo "=== Installed SDK Packages ===" && sdkmanager --list_installed
EOF
    chmod +x /usr/local/bin/check-react-native 2>/dev/null || true
fi

if [ "${ENABLE_PYTHON:-}" = "1" ]; then
    VENV_DIR="$TARGET_DIR/.venv"
    if [ ! -d "$VENV_DIR" ]; then
        echo "🐍 Creating virtual environment at $VENV_DIR..."
        python3 -m venv "$VENV_DIR"
    fi

    grep -qxF "source $VENV_DIR/bin/activate" ~/.bashrc 2>/dev/null || echo "source $VENV_DIR/bin/activate" >> ~/.bashrc
    grep -qxF "VIRTUAL_ENV=\"$VENV_DIR\"" /etc/environment 2>/dev/null || echo "VIRTUAL_ENV=\"$VENV_DIR\"" >> /etc/environment

    # Also persist to /etc/profile.d for system-wide login shell activation
    cat << EOF > /etc/profile.d/python-venv.sh
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
fi
EOF
    chmod +x /etc/profile.d/python-venv.sh 2>/dev/null || true

    # Quick verification banner
    PYTHON_VER=$("$VENV_DIR/bin/python3" --version 2>&1 | cut -d' ' -f2 || echo "Not found")
    PIP_VER=$("$VENV_DIR/bin/pip" --version 2>&1 | cut -d' ' -f2 || echo "Not found")

    echo "🐍 Python Tooling Active:"
    echo "   • Virtualenv: $VENV_DIR"
    echo "   • Python: $PYTHON_VER"
    echo "   • Pip: $PIP_VER"

    # Install on-demand inspection utility
    cat << EOF > /usr/local/bin/check-python
#!/usr/bin/env bash
echo "=== Python ===" && "$VENV_DIR/bin/python3" --version
echo "=== Pip ===" && "$VENV_DIR/bin/pip" --version
echo "=== Virtual Environment ===" && echo "VIRTUAL_ENV: \${VIRTUAL_ENV:-$VENV_DIR}"
echo "=== Installed Packages in .venv ===" && "$VENV_DIR/bin/pip" list
EOF
    chmod +x /usr/local/bin/check-python 2>/dev/null || true
fi

# 2. Decrypt / write environment keys if provided
if [ -n "${DOTENV_PRIVATE_KEY:-}" ]; then
    echo "DOTENV_PRIVATE_KEY=$DOTENV_PRIVATE_KEY" > .env.keys
fi

if [ "${ENABLE_SOPS:-}" = "1" ]; then
    if [ -z "${AGE_PRIVATE_KEY:-}" ]; then
        echo "ERROR: SOPS decryption is enabled (via --sops or --agy), but AGE_PRIVATE_KEY is not set in the environment." >&2
        exit 1
    fi

    mkdir -p ~/.config/sops/age
    echo "$AGE_PRIVATE_KEY" > ~/.config/sops/age/keys.txt
    chmod 600 ~/.config/sops/age/keys.txt

    setup_status=0
    if [ -f "scripts/setup.sh" ]; then
        echo "🔐 Decrypting secrets with SOPS..."
        bash scripts/setup.sh || setup_status=$?
    fi

    rm -rf ~/.config/sops
    echo "🧹 Purged temporary SOPS credentials (~/.config/sops)."
    grep -qxF "unset AGE_PRIVATE_KEY" ~/.bashrc 2>/dev/null || echo "unset AGE_PRIVATE_KEY" >> ~/.bashrc
    unset AGE_PRIVATE_KEY

    if [ "$setup_status" -ne 0 ]; then
        echo "ERROR: scripts/setup.sh failed to execute (exit code: $setup_status)." >&2
        exit "$setup_status"
    fi
fi

# 3. Install dependencies if package manifest exists
if [ -f "pnpm-lock.yaml" ]; then
    pnpm install
elif [ -f "package.json" ]; then
    npm install
fi

if [ "${ENABLE_PYTHON:-}" = "1" ] && [ -f "requirements.txt" ]; then
    echo "📦 Installing Python dependencies from requirements.txt into .venv..."
    "$TARGET_DIR/.venv/bin/pip" install -r requirements.txt
fi

# 4. Keep the sandbox alive for interaction via modal shell / ssh, or run the
#    OpenCode server when requested.
echo "🏝️  Sandbox Ready!"
if [ "${ENABLE_OPENCODE:-}" = "1" ]; then
    OPENCODE_PORT="${OPENCODE_PORT:-4096}"
    echo "🏝️  Starting OpenCode server on port $OPENCODE_PORT..."
    nohup opencode serve --hostname 0.0.0.0 --port "$OPENCODE_PORT" > /tmp/opencode.log 2>&1 &
fi
exec sleep infinity
