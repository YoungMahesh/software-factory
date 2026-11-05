#!/usr/bin/env bash
set -euo pipefail

BRANCH="${1:-main}"

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

# Start Cloudflare Tunnel service and port watcher if enabled (default: enabled)
if [ "${ENABLE_CLOUDFLARE:-1}" != "0" ]; then
    if [ -z "${AGE_PRIVATE_KEY:-}" ]; then
        echo "ERROR: Cloudflare Tunnel is enabled, but AGE_PRIVATE_KEY is not set in the environment. Ensure the Modal secret 'share0' is configured with AGE_PRIVATE_KEY or launch with --no-cloudflare." >&2
        exit 1
    fi

    CLOUDFLARE_SECRET_FILE="/root/secrets/cloudflare.env"
    if [ ! -f "$CLOUDFLARE_SECRET_FILE" ]; then
        echo "ERROR: Cloudflare Tunnel secret file not found at $CLOUDFLARE_SECRET_FILE." >&2
        exit 1
    fi

    echo "🚇 Decrypting Cloudflare Tunnel token from $CLOUDFLARE_SECRET_FILE..."
    CF_TOKEN=$(SOPS_AGE_KEY="$AGE_PRIVATE_KEY" sops decrypt --extract '["CF_TOKEN"]' "$CLOUDFLARE_SECRET_FILE" 2>/dev/null || true)
    if [ -z "$CF_TOKEN" ]; then
        echo "ERROR: Failed to decrypt CF_TOKEN from $CLOUDFLARE_SECRET_FILE using AGE_PRIVATE_KEY." >&2
        exit 1
    fi

    if [ ! -f /etc/init.d/cloudflared ]; then
        echo "🚇 Installing Cloudflare Tunnel service..."
        cloudflared service install "$CF_TOKEN"
    elif [ -f /etc/cloudflared/token ]; then
        CURRENT_TOKEN=$(cat /etc/cloudflared/token 2>/dev/null || true)
        if [ "$CURRENT_TOKEN" != "$CF_TOKEN" ]; then
            echo "$CF_TOKEN" > /etc/cloudflared/token
        fi
    fi

    # Patch /etc/init.d/cloudflared to reject zombie processes so stop/status/start
    # correctly handle defunct child processes in container environments where PID 1
    # does not reap re-parented child zombies.
    if [ -f /etc/init.d/cloudflared ]; then
        sed -i 's|\[ -f "$pid_file" \] && ps $(get_pid) > /dev/null 2>&1|[ -f "$pid_file" ] \&\& [ -d "/proc/$(get_pid)" ] \&\& ! grep -q "^State:[[:space:]]*Z" "/proc/$(get_pid)/status" 2>/dev/null|' /etc/init.d/cloudflared
    fi

    # Initially stop the service until the target web port actually opens
    /etc/init.d/cloudflared stop >/dev/null 2>&1 || true
    rm -f /var/run/cloudflared.pid

    # Port watcher daemon: starts cloudflared only when the port is listening,
    # and immediately stops it when the app stops, preventing traffic hijacking.
    cat << 'EOF' > /usr/local/bin/cloudflared-port-watcher
#!/usr/bin/env bash
TARGET_PORT="${1:-3000}"
CHECK_INTERVAL=2

while true; do
    TARGET_HEX=$(printf "%04X" "$TARGET_PORT")
    if grep -q -E ":${TARGET_HEX} [0-9A-F:]+ 0A" /proc/net/tcp /proc/net/tcp6 2>/dev/null; then
        # Port is OPEN: ensure cloudflared is running
        if ! /etc/init.d/cloudflared status >/dev/null 2>&1; then
            echo "[$(date +%T)] 🚇 Port $TARGET_PORT is active. Starting Cloudflare Tunnel..."
            /etc/init.d/cloudflared start >/dev/null 2>&1 || true
        fi
    else
        # Port is CLOSED: ensure cloudflared is stopped so it doesn't take traffic
        if /etc/init.d/cloudflared status >/dev/null 2>&1; then
            echo "[$(date +%T)] 🚇 Port $TARGET_PORT is closed. Stopping Cloudflare Tunnel..."
            /etc/init.d/cloudflared stop >/dev/null 2>&1 || true
        fi
    fi
    sleep "$CHECK_INTERVAL"
done
EOF
    chmod +x /usr/local/bin/cloudflared-port-watcher

    nohup /usr/local/bin/cloudflared-port-watcher "${PORT:-3000}" > /var/log/cloudflared-watcher.log 2>&1 &
fi

# Start Docker daemon in background if enabled (VM Sandbox)
if [ "${ENABLE_DOCKER:-}" = "1" ]; then
    echo "Starting dockerd..."
    /usr/bin/dockerd > /var/log/dockerd.log 2>&1 &
    # Wait for Docker daemon to become ready (up to 30s)
    echo "Waiting for dockerd to be ready..."
    for i in $(seq 1 30); do
        if [ -S /var/run/docker.sock ] && docker info >/dev/null 2>&1; then
            echo "Docker is ready!"
            break
        fi
        if [ "$i" -eq 30 ]; then
            echo "ERROR: dockerd failed to start within 30s. Logs:" >&2
            cat /var/log/dockerd.log >&2
            exit 1
        fi
        sleep 1
    done
fi

# 1. Decrypt repository fetch secret or organization token and clone repository
if [ "${RESUME_SNAPSHOT:-0}" = "1" ]; then
    echo "♻️  Resuming from filesystem snapshot..."

    # Optional: Decrypt repository fetch secret or organization token if present
    if [ -n "${AGE_PRIVATE_KEY:-}" ]; then
        if [ -f "/root/secrets/github-orgs.env" ]; then
            echo "🔐 Resolving organization credentials from /root/secrets/github-orgs.env..."
            ORG_NAME="${GH_ORG:-}"
            if [ -z "$ORG_NAME" ] && [[ "${GH_REPO:-}" =~ ^([^/]+)/ ]]; then
                ORG_NAME="${BASH_REMATCH[1]}"
            fi
            ORG_NAME="${ORG_NAME:-sFactory0}"
            ORG_VAR=$(printf '%s' "$ORG_NAME" | tr '[:lower:]' '[:upper:]' | tr -c '[:alnum:]' '_')
            TOKEN_VAR="${ORG_VAR}_GH_TOKEN"
            DECRYPTED_ORGS=$(SOPS_AGE_KEY="$AGE_PRIVATE_KEY" sops decrypt "/root/secrets/github-orgs.env" 2>/dev/null || true)
            if [ -n "$DECRYPTED_ORGS" ]; then
                GH_TOKEN=$(echo "$DECRYPTED_ORGS" | grep -E "^[[:space:]]*${TOKEN_VAR}=" | head -n1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d '\r\n' || true)
                if [ -z "$GH_TOKEN" ]; then
                    GH_TOKEN=$(echo "$DECRYPTED_ORGS" | grep -E "^[[:space:]]*GH_TOKEN=" | head -n1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d '\r\n' || true)
                fi
                if [ -z "$GH_TOKEN" ]; then
                    GH_TOKEN=$(echo "$DECRYPTED_ORGS" | grep -E "^[[:space:]]*SFACTORY0_GH_TOKEN=" | head -n1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d '\r\n' || true)
                fi
                [ -n "$GH_TOKEN" ] && export GH_TOKEN
            fi
            rm -f /root/secrets/github-orgs.env
            export ORG_TOKEN="1"
            export TRACKER="${TRACKER:-github}"
        fi
    fi

    # Discover target directory
    TARGET_DIR=""
    if [ -n "${GH_REPO:-}" ]; then
        REPO_NAME=$(basename "$GH_REPO")
        if [ -d "/root/$REPO_NAME" ]; then
            TARGET_DIR="/root/$REPO_NAME"
        fi
    fi
    if [ -z "$TARGET_DIR" ]; then
        for d in /root/*/; do
            if [ -d "${d}.git" ]; then
                TARGET_DIR="${d%/}"
                break
            fi
        done
    fi
    TARGET_DIR="${TARGET_DIR:-/root}"
    echo "📁 Workspace resolved to $TARGET_DIR"
    cd "$TARGET_DIR"
else
    if [ "${NO_REPO:-0}" = "1" ]; then
        echo "🏝️  No repository provided: skipping repository fetch."
        TARGET_DIR="/root/${APP_NAME:-sandbox}"
        mkdir -p "$TARGET_DIR"
        cd "$TARGET_DIR"
        if [ ! -d "$TARGET_DIR/.git" ]; then
            echo "🌱 Initializing empty Git repository with branch main in $TARGET_DIR..."
            git init -b main "$TARGET_DIR"
            cat << 'EOF' > "$TARGET_DIR/.gitignore"
.env
.env.*
node_modules/
dist/
.venv/
__pycache__/
*.pyc
EOF
            git -C "$TARGET_DIR" add .gitignore
            GIT_AUTHOR_NAME="${GIT_AUTHOR_NAME:-Mahesh}" \
            GIT_AUTHOR_EMAIL="${GIT_AUTHOR_EMAIL:-maheshghamand@gmail.com}" \
            GIT_COMMITTER_NAME="${GIT_COMMITTER_NAME:-Mahesh}" \
            GIT_COMMITTER_EMAIL="${GIT_COMMITTER_EMAIL:-maheshghamand@gmail.com}" \
            git -C "$TARGET_DIR" commit -m "initial commit"
        fi
        echo "📁 Workspace resolved to $TARGET_DIR"
    else
        if [ -z "${AGE_PRIVATE_KEY:-}" ]; then
            echo "ERROR: AGE_PRIVATE_KEY is not set in the environment. Ensure the Modal secret 'share0' is configured with AGE_PRIVATE_KEY." >&2
            exit 1
        fi

        if [ -f "/root/secrets/github-orgs.env" ]; then
            if [ -z "${GH_REPO:-}" ]; then
                echo "ERROR: GH_REPO environment variable is required when using organization credentials." >&2
                exit 1
            fi
            echo "🔐 Resolving organization credentials from /root/secrets/github-orgs.env..."
            ORG_NAME="${GH_ORG:-}"
            if [ -z "$ORG_NAME" ] && [[ "$GH_REPO" =~ ^([^/]+)/ ]]; then
                ORG_NAME="${BASH_REMATCH[1]}"
            fi
            ORG_NAME="${ORG_NAME:-sFactory0}"
            ORG_VAR=$(printf '%s' "$ORG_NAME" | tr '[:lower:]' '[:upper:]' | tr -c '[:alnum:]' '_')
            TOKEN_VAR="${ORG_VAR}_GH_TOKEN"

            DECRYPTED_ORGS=$(SOPS_AGE_KEY="$AGE_PRIVATE_KEY" sops decrypt "/root/secrets/github-orgs.env" 2>/dev/null || true)
            if [ -z "$DECRYPTED_ORGS" ]; then
                echo "ERROR: Failed to decrypt /root/secrets/github-orgs.env using AGE_PRIVATE_KEY." >&2
                rm -f /root/secrets/github-orgs.env
                exit 1
            fi

            GH_TOKEN=$(echo "$DECRYPTED_ORGS" | grep -E "^[[:space:]]*${TOKEN_VAR}=" | head -n1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d '\r\n' || true)
            if [ -z "$GH_TOKEN" ]; then
                GH_TOKEN=$(echo "$DECRYPTED_ORGS" | grep -E "^[[:space:]]*GH_TOKEN=" | head -n1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d '\r\n' || true)
            fi
            if [ -z "$GH_TOKEN" ]; then
                GH_TOKEN=$(echo "$DECRYPTED_ORGS" | grep -E "^[[:space:]]*SFACTORY0_GH_TOKEN=" | head -n1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d '\r\n' || true)
            fi

            if [ -z "$GH_TOKEN" ]; then
                echo "ERROR: Could not find $TOKEN_VAR in /root/secrets/github-orgs.env." >&2
                rm -f /root/secrets/github-orgs.env
                exit 1
            fi

            rm -f /root/secrets/github-orgs.env
            echo "🧹 Purged encrypted organization secrets file from disk."
            export ORG_TOKEN="1"
            export TRACKER="${TRACKER:-github}"
        else
            echo "ERROR: Organization credentials not found at /root/secrets/github-orgs.env." >&2
            exit 1
        fi

        if [ -z "${GH_REPO:-}" ]; then
            echo "ERROR: GH_REPO is not set." >&2
            exit 1
        fi

        if [[ "$GH_REPO" != *"/"* ]]; then
            GH_REPO="sFactory0/$GH_REPO"
        fi

        if [ -z "${GH_TOKEN:-}" ]; then
            echo "ERROR: GH_TOKEN is not set." >&2
            exit 1
        fi

        REPO_NAME=$(basename "$GH_REPO")
        TARGET_DIR="/root/$REPO_NAME"

        if [ ! -d "$TARGET_DIR" ]; then
            echo "🏝️  Cloning $GH_REPO (branch: $BRANCH)..."
            if [ "${FULL_CLONE:-0}" = "1" ]; then
                GIT_ASKPASS=echo git clone --quiet --branch "$BRANCH" --single-branch \
                    "https://oauth2:${GH_TOKEN}@github.com/${GH_REPO}.git" "$TARGET_DIR"
            else
                GIT_ASKPASS=echo git clone --quiet --depth 50 --branch "$BRANCH" --single-branch \
                    "https://oauth2:${GH_TOKEN}@github.com/${GH_REPO}.git" "$TARGET_DIR"
            fi
        fi

        cd "$TARGET_DIR"

        if ! git symbolic-ref -q HEAD >/dev/null; then
            echo "ERROR: '$BRANCH' resolved to a tag or detached commit. Only Git branches are supported." >&2
            exit 1
        fi
    fi
fi

# Decrypt repository environment secrets if env.map is present
ENV_MAP_FILE=""
SECRETS_DIR=""
if [ -f "$TARGET_DIR/.secrets/env.map" ]; then
    ENV_MAP_FILE="$TARGET_DIR/.secrets/env.map"
    SECRETS_DIR="$TARGET_DIR/.secrets"
fi

if [ -n "$ENV_MAP_FILE" ] && [ -f "$ENV_MAP_FILE" ]; then
    echo "📄 Decrypting repository environment secrets into $TARGET_DIR..."
    while IFS= read -r line || [ -n "$line" ]; do
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "${line// }" ]] && continue
        if [[ "$line" =~ ^([^=]+)=(.*)$ ]]; then
            src_rel="${BASH_REMATCH[1]}"
            dest_rel="${BASH_REMATCH[2]}"
            # Trim whitespace and carriage returns
            src_rel=$(echo "$src_rel" | tr -d '\r' | xargs)
            dest_rel=$(echo "$dest_rel" | tr -d '\r' | xargs)
            dest_rel="${dest_rel#/}"

            src_file="$SECRETS_DIR/$src_rel"
            dest_file="$TARGET_DIR/$dest_rel"

            if [ ! -f "$src_file" ]; then
                echo "ERROR: Mapped repository secret file not found at $src_file." >&2
                [ "$SECRETS_DIR" = "/root/secrets/repo" ] && rm -rf /root/secrets/repo
                exit 1
            fi

            mkdir -p "$(dirname "$dest_file")"
            if ! SOPS_AGE_KEY="$AGE_PRIVATE_KEY" sops decrypt "$src_file" > "$dest_file"; then
                echo "ERROR: Failed to decrypt $src_file using AGE_PRIVATE_KEY." >&2
                rm -f "$dest_file"
                [ "$SECRETS_DIR" = "/root/secrets/repo" ] && rm -rf /root/secrets/repo
                exit 1
            fi
            chmod 600 "$dest_file"
            echo "   • Decrypted $src_rel -> $dest_rel"
        fi
    done < "$ENV_MAP_FILE"
fi

if [ -f /root/secrets/github-orgs.env ]; then
    rm -f /root/secrets/github-orgs.env
    echo "🧹 Purged organization secrets staging file (/root/secrets/github-orgs.env)."
fi
if [ -f /root/.bash_aliases ]; then
    grep -qxF "source /root/.bash_aliases" ~/.bashrc 2>/dev/null || echo "source /root/.bash_aliases" >> ~/.bashrc
fi
grep -qxF "export HOSTNAME=0.0.0.0" ~/.bashrc 2>/dev/null || echo "export HOSTNAME=0.0.0.0" >> ~/.bashrc
grep -qxF "export PORT=${PORT:-3000}" ~/.bashrc 2>/dev/null || echo "export PORT=${PORT:-3000}" >> ~/.bashrc

# sshd builds a clean environment for login sessions, so image-level PATH alone
# does not reach interactive shells.
if [ "${ENABLE_OPENCODE:-}" = "1" ]; then
    grep -qxF 'export PATH="/root/.opencode/bin:$PATH"' ~/.bashrc 2>/dev/null || echo 'export PATH="/root/.opencode/bin:$PATH"' >> ~/.bashrc
fi
if [ "${ENABLE_ANTIGRAVITY:-}" = "1" ]; then
    grep -qxF 'export PATH="/root/.local/bin:$PATH"' ~/.bashrc 2>/dev/null || echo 'export PATH="/root/.local/bin:$PATH"' >> ~/.bashrc
    grep -qxF "alias agy='agy --dangerously-skip-permissions'" ~/.bashrc 2>/dev/null || echo "alias agy='agy --dangerously-skip-permissions'" >> ~/.bashrc
fi
if [ "${ENABLE_T3:-}" = "1" ]; then
    grep -qxF 'export PATH="/usr/local/bin:$PATH"' ~/.bashrc 2>/dev/null || echo 'export PATH="/usr/local/bin:$PATH"' >> ~/.bashrc
fi
if [ "${ENABLE_HERDR:-}" = "1" ]; then
    grep -qxF 'export PATH="/usr/local/bin:$PATH"' ~/.bashrc 2>/dev/null || echo 'export PATH="/usr/local/bin:$PATH"' >> ~/.bashrc
fi

if [ "${ENABLE_REACT_NATIVE:-}" = "1" ]; then
    # Increase inotify file watch limit for React Native / Expo bundler
    if ! sysctl -w fs.inotify.max_user_watches=524288 2>/dev/null; then
        echo "⚠️  Warning: Unable to set fs.inotify.max_user_watches=524288. If using React Native / Metro, consider launching with --vm."
    fi
    mkdir -p /etc/sysctl.d 2>/dev/null || true
    echo "fs.inotify.max_user_watches=524288" > /etc/sysctl.d/99-react-native.conf 2>/dev/null || true

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

    # Quick verification banner
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
echo "=== Watchman ===" && (watchman --version 2>/dev/null || echo "Watchman not found")
echo "=== Inotify Watch Limit ===" && sysctl fs.inotify.max_user_watches
echo "=== Expo Ngrok ===" && (npm list -g @expo/ngrok --depth=0 2>/dev/null || echo "Not installed")
echo "=== Environment Variables ===" && echo "JAVA_HOME: $JAVA_HOME" && echo "ANDROID_HOME: $ANDROID_HOME"
echo "=== Installed SDK Packages ===" && sdkmanager --list_installed
EOF
    chmod +x /usr/local/bin/check-react-native 2>/dev/null || true
fi

if [ "${ENABLE_MODAL:-}" = "1" ]; then
    VENV_DIR="$TARGET_DIR/.venv"
    if [ ! -d "$VENV_DIR" ]; then
        echo "⚡ Creating virtual environment at $VENV_DIR..."
        uv venv --seed "$VENV_DIR"
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

    echo "⚡ Installing Modal client package into .venv..."
    uv pip install --python "$VENV_DIR/bin/python" --quiet modal

    # Quick verification banner
    PYTHON_VER=$("$VENV_DIR/bin/python3" --version 2>&1 | cut -d' ' -f2 || echo "Not found")
    PIP_VER=$("$VENV_DIR/bin/pip" --version 2>&1 | cut -d' ' -f2 || echo "Not found")
    MODAL_VER=$("$VENV_DIR/bin/modal" --version 2>&1 | cut -d' ' -f3 || echo "Installed")

    echo "⚡ Modal Development Tooling Active:"
    echo "   • Virtualenv: $VENV_DIR"
    echo "   • Python: $PYTHON_VER"
    echo "   • Pip: $PIP_VER"
    echo "   • Modal SDK: $MODAL_VER"

    # Install on-demand inspection utility
    cat << EOF > /usr/local/bin/check-modal
#!/usr/bin/env bash
echo "=== Python ===" && "$VENV_DIR/bin/python3" --version
echo "=== Pip ===" && "$VENV_DIR/bin/pip" --version
echo "=== Virtual Environment ===" && echo "VIRTUAL_ENV: \${VIRTUAL_ENV:-$VENV_DIR}"
echo "=== Modal CLI ===" && "$VENV_DIR/bin/modal" --version
echo "=== Modal Profile ===" && ("$VENV_DIR/bin/modal" profile current 2>/dev/null || echo "Configured at ~/.modal.toml")
echo "=== Installed Packages in .venv ===" && "$VENV_DIR/bin/pip" list
EOF
    chmod +x /usr/local/bin/check-modal 2>/dev/null || true
    ln -sf /usr/local/bin/check-modal /usr/local/bin/check-python
fi

if [ "${ENABLE_BROWSER:-}" = "1" ]; then
    CHROME_BIN="/opt/google/chrome/chrome"
    if [ -x "$CHROME_BIN" ]; then
        CHROME_VER=$("$CHROME_BIN" --version 2>/dev/null | awk '{print $3}' || echo "unknown")
        echo "🌐 Browser Tooling Active:"
        echo "   • Chrome: $CHROME_BIN (v${CHROME_VER:-unknown})"
        echo "   • MCP: Playwright & Chrome DevTools (headless, sandbox-free)"
    else
        echo "⚠️  Browser Tooling enabled but Chrome was not found at $CHROME_BIN" >&2
    fi

    # Install on-demand inspection utility
    cat << 'EOF' > /usr/local/bin/check-browser
#!/usr/bin/env bash
CHROME_BIN="/opt/google/chrome/chrome"
echo "=== Chrome Binary ===" && ls -l "$CHROME_BIN"
echo "=== Chrome Version ===" && "$CHROME_BIN" --version
echo "=== Headless Smoke Test ===" && "$CHROME_BIN" --headless --no-sandbox --disable-dev-shm-usage --dump-dom about:blank
echo "=== MCP Runtime ===" && node --version && npx --version
EOF
    chmod +x /usr/local/bin/check-browser 2>/dev/null || true
fi

if [ "${ENABLE_ANTIGRAVITY:-}" = "1" ]; then
    cat << 'EOF' > /usr/local/bin/check-antigravity
#!/usr/bin/env bash
echo "=== Antigravity CLI ===" && agy --version 2>/dev/null || true
echo "=== Antigravity Remote Control Status ===" && agy remote-control status 2>/dev/null || true
echo "=== Antigravity Settings ===" && cat ~/.gemini/antigravity-cli/settings.json 2>/dev/null || true
echo "=== Antigravity Onboarding ===" && cat ~/.gemini/antigravity-cli/cache/onboarding.json 2>/dev/null || true
echo "=== OAuth Token ===" && ls -la ~/.gemini/antigravity-cli/antigravity-oauth-token 2>/dev/null || true
EOF
    chmod +x /usr/local/bin/check-antigravity 2>/dev/null || true
    ln -sf /usr/local/bin/check-antigravity /usr/local/bin/check-agy
fi

if [ "${ENABLE_T3:-}" = "1" ]; then
    cat << 'EOF' > /usr/local/bin/check-t3
#!/usr/bin/env bash
echo "=== T3 Code Binary ===" && which t3 && t3 --version
echo "=== GitHub CLI ===" && (which gh && gh --version || echo "gh not found")
echo "=== GitHub Auth Status ===" && (gh auth status 2>&1 || true)
echo "=== T3 Public URL ===" && cat /root/.t3/public_url 2>/dev/null || true
echo "=== T3 Runtime State ===" && cat /root/.t3/userdata/server-runtime.json 2>/dev/null || true
echo "=== T3 Code Process ===" && ps aux | grep [t]3
echo "=== T3 Server Log ===" && tail -n 20 /tmp/t3.log 2>/dev/null || true
echo "=== Listening Sockets ===" && (ss -tulpn 2>/dev/null | grep 3775 || netstat -tulpn 2>/dev/null | grep 3775 || true)
echo "=== T3 Settings ===" && cat /root/.t3/userdata/settings.json 2>/dev/null || true
echo "=== T3 Antigravity Token ===" && ls -la /root/.t3/userdata/providers/antigravity/*/antigravity-acp/acp_token.json 2>/dev/null || true
echo "=== T3 OpenCode Config ===" && ls -la /root/.config/opencode/opencode.json /root/.config/opencode/opencode.env 2>/dev/null || true
EOF
    chmod +x /usr/local/bin/check-t3 2>/dev/null || true
fi

if [ "${ENABLE_CLOUDFLARE:-1}" != "0" ]; then
    cat << 'EOF' > /usr/local/bin/check-cloudflare
#!/usr/bin/env bash
echo "=== Cloudflared Version ===" && cloudflared --version
echo "=== Service Status ===" && /etc/init.d/cloudflared status
echo "=== Process ===" && ps aux | grep [c]loudflared
echo "=== Port Watcher Process ===" && ps aux | grep [c]loudflared-port-watcher
echo "=== Port Watcher Log ===" && cat /var/log/cloudflared-watcher.log 2>/dev/null || true
echo "=== Config / Token ===" && ls -la /etc/cloudflared/
echo "=== Secret File ===" && ls -la /root/secrets/cloudflare.env 2>/dev/null || true
EOF
    chmod +x /usr/local/bin/check-cloudflare 2>/dev/null || true
    ln -sf /usr/local/bin/check-cloudflare /usr/local/bin/check-cf
fi

# 2. Decrypt / write environment keys if provided
if [ -n "${DOTENV_PRIVATE_KEY:-}" ]; then
    echo "DOTENV_PRIVATE_KEY=$DOTENV_PRIVATE_KEY" > .env.keys
fi

if [ "${ENABLE_ANTIGRAVITY:-}" = "1" ] || [ "${ENABLE_MODAL:-}" = "1" ] || [ "${ENABLE_OPENCODE:-}" = "1" ] || [ "${ENABLE_SOPS:-}" = "1" ] || [ "${ENABLE_PI:-}" = "1" ] || [ "${ENABLE_T3:-}" = "1" ]; then
    if [ "${RESUME_SNAPSHOT:-0}" != "1" ]; then
        if [ -z "${AGE_PRIVATE_KEY:-}" ]; then
            if [ "${ENABLE_T3:-}" = "1" ] && [ "${ENABLE_ANTIGRAVITY:-0}" != "1" ] && [ "${ENABLE_MODAL:-0}" != "1" ] && [ "${ENABLE_OPENCODE:-0}" != "1" ] && [ "${ENABLE_SOPS:-0}" != "1" ] && [ "${ENABLE_PI:-0}" != "1" ]; then
                echo "⚠️  Warning: AGE_PRIVATE_KEY not set in environment. Skipping OpenCode credentials decryption for T3 Code." >&2
            else
                echo "ERROR: Credentials decryption requested (--agy, --modal, --opencode, --pi, --sops, or --t3), but AGE_PRIVATE_KEY is not set in the environment. Ensure the Modal secret 'share0' is configured with AGE_PRIVATE_KEY." >&2
                exit 1
            fi
        fi

        if [ -n "${AGE_PRIVATE_KEY:-}" ]; then
            mkdir -p ~/.config/sops/age
            echo "$AGE_PRIVATE_KEY" > ~/.config/sops/age/keys.txt
            chmod 600 ~/.config/sops/age/keys.txt

            if [ -f "/root/secrets/antigravity.env" ]; then
                while IFS= read -r line || [ -n "$line" ]; do
                    [[ "$line" =~ ^[[:space:]]*# ]] && continue
                    [[ -z "${line// }" ]] && continue
                    export "$line"
                done < <(SOPS_AGE_KEY="$AGE_PRIVATE_KEY" sops decrypt "/root/secrets/antigravity.env" 2>/dev/null || true)
            fi

            setup_args=()
            if [ "${ENABLE_MODAL:-}" = "1" ]; then
                setup_args+=("--modal")
            fi
            if [ "${ENABLE_ANTIGRAVITY:-}" = "1" ]; then
                setup_args+=("--agy")
            fi
            if [ "${ENABLE_T3:-}" = "1" ]; then
                setup_args+=("--t3")
            fi
            if [ "${ENABLE_OPENCODE:-}" = "1" ] || [ "${ENABLE_T3:-}" = "1" ]; then
                setup_args+=("--opencode")
            fi
            if [ "${ENABLE_PI:-}" = "1" ]; then
                setup_args+=("--pi")
            fi

            setup_status=0
            if [ ${#setup_args[@]} -gt 0 ] && [ -f "/root/scripts/setup.sh" ]; then
                echo "🔐 Decrypting tooling credentials with SOPS..."
                bash /root/scripts/setup.sh "${setup_args[@]}" || setup_status=$?
            fi
        fi
    fi
fi

# Scrub staged encrypted tooling secrets immediately after decryption
rm -f /root/secrets/opencode.env /root/secrets/antigravity-oauth-token*.json /root/secrets/modal.toml /root/secrets/antigravity.env

if [ "${ENABLE_SOPS:-}" = "1" ]; then
    echo "🔐 SOPS credentials retained in sandbox (~/.config/sops/age/keys.txt)."
    export SOPS_AGE_KEY_FILE="/root/.config/sops/age/keys.txt"
    export SOPS_AGE_KEY="$AGE_PRIVATE_KEY"

    grep -qxF 'export SOPS_AGE_KEY_FILE="/root/.config/sops/age/keys.txt"' ~/.bashrc 2>/dev/null || echo 'export SOPS_AGE_KEY_FILE="/root/.config/sops/age/keys.txt"' >> ~/.bashrc
    grep -qxF "export SOPS_AGE_KEY=\"$AGE_PRIVATE_KEY\"" ~/.bashrc 2>/dev/null || echo "export SOPS_AGE_KEY=\"$AGE_PRIVATE_KEY\"" >> ~/.bashrc
    grep -qxF "export AGE_PRIVATE_KEY=\"$AGE_PRIVATE_KEY\"" ~/.bashrc 2>/dev/null || echo "export AGE_PRIVATE_KEY=\"$AGE_PRIVATE_KEY\"" >> ~/.bashrc

    # Also persist to /etc/environment for non-interactive / login session consistency
    grep -qxF 'SOPS_AGE_KEY_FILE="/root/.config/sops/age/keys.txt"' /etc/environment 2>/dev/null || echo 'SOPS_AGE_KEY_FILE="/root/.config/sops/age/keys.txt"' >> /etc/environment
    grep -qxF "SOPS_AGE_KEY=\"$AGE_PRIVATE_KEY\"" /etc/environment 2>/dev/null || echo "SOPS_AGE_KEY=\"$AGE_PRIVATE_KEY\"" >> /etc/environment
    grep -qxF "AGE_PRIVATE_KEY=\"$AGE_PRIVATE_KEY\"" /etc/environment 2>/dev/null || echo "AGE_PRIVATE_KEY=\"$AGE_PRIVATE_KEY\"" >> /etc/environment

    # Also persist to /etc/profile.d for system-wide login shell activation
    cat << EOF > /etc/profile.d/sops.sh
export SOPS_AGE_KEY_FILE="/root/.config/sops/age/keys.txt"
export SOPS_AGE_KEY="$AGE_PRIVATE_KEY"
export AGE_PRIVATE_KEY="$AGE_PRIVATE_KEY"
EOF
    chmod +x /etc/profile.d/sops.sh 2>/dev/null || true

    # Install on-demand inspection utility
    cat << 'EOF' > /usr/local/bin/check-sops
#!/usr/bin/env bash
echo "=== SOPS Version ===" && sops --version
echo "=== Age Key File ===" && ls -la ~/.config/sops/age/keys.txt 2>/dev/null || echo "Missing"
echo "=== Environment Variables ==="
echo "SOPS_AGE_KEY_FILE: ${SOPS_AGE_KEY_FILE:-}"
echo "SOPS_AGE_KEY: ${SOPS_AGE_KEY:+[SET]}"
echo "AGE_PRIVATE_KEY: ${AGE_PRIVATE_KEY:+[SET]}"
if [ -f ~/.config/sops/age/keys.txt ]; then
    echo "Key file exists and contains $(wc -l < ~/.config/sops/age/keys.txt) lines."
fi
EOF
    chmod +x /usr/local/bin/check-sops 2>/dev/null || true
else
    # Unconditionally scrub AGE_PRIVATE_KEY and temporary SOPS state across all sandboxes
    if [ -n "${AGE_PRIVATE_KEY:-}" ] || [ -d ~/.config/sops ]; then
        rm -rf ~/.config/sops
        echo "🧹 Purged temporary SOPS credentials (~/.config/sops)."
        grep -qxF "unset AGE_PRIVATE_KEY" ~/.bashrc 2>/dev/null || echo "unset AGE_PRIVATE_KEY" >> ~/.bashrc
        unset AGE_PRIVATE_KEY
    fi
fi

# Manage repository credentials based on tooling requirements
if [ "${ENABLE_T3:-0}" = "1" ] && [ -n "${GH_TOKEN:-}" ]; then
    echo "🔐 T3 Code enabled: retaining GH_TOKEN in process environment for T3 Code."
    export GH_TOKEN
    grep -qxF "export GH_TOKEN="$GH_TOKEN"" ~/.bashrc 2>/dev/null || echo "export GH_TOKEN="$GH_TOKEN"" >> ~/.bashrc
    grep -qxF "GH_TOKEN="$GH_TOKEN"" /etc/environment 2>/dev/null || echo "GH_TOKEN="$GH_TOKEN"" >> /etc/environment
else
    # Unconditionally scrub GH_TOKEN and ephemeral repository credentials from memory
    grep -qxF "unset GH_TOKEN" ~/.bashrc 2>/dev/null || echo "unset GH_TOKEN" >> ~/.bashrc
    grep -qxF "unset DOTENV_PRIVATE_KEY" ~/.bashrc 2>/dev/null || echo "unset DOTENV_PRIVATE_KEY" >> ~/.bashrc
    unset GH_TOKEN 2>/dev/null || true
    unset DOTENV_PRIVATE_KEY 2>/dev/null || true
    unset DECRYPTED_FETCH 2>/dev/null || true
fi

if [ "${setup_status:-0}" -ne 0 ]; then
    echo "ERROR: /root/scripts/setup.sh failed to execute (exit code: $setup_status)." >&2
    exit "$setup_status"
fi

# Allocate swap space if requested (VM Sandbox only, e.g. SWAP_GB > 0)
if [ -n "${SWAP_GB:-}" ] && [ "$SWAP_GB" -gt 0 ] 2>/dev/null; then
    if ! swapon --show | grep -q '/swapfile'; then
        echo "Allocating ${SWAP_GB} GB swapfile..."
        fallocate -l "${SWAP_GB}G" /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=$((SWAP_GB * 1024))
        chmod 600 /swapfile
        mkswap /swapfile
        swapon /swapfile
    fi
fi

# 3. Install dependencies if package manifest exists
if [ "${RESUME_SNAPSHOT:-0}" != "1" ]; then
    if [ -f "pnpm-lock.yaml" ]; then
        pnpm install
    elif [ -f "package.json" ]; then
        npm install
    fi

    if [ "${ENABLE_MODAL:-}" = "1" ] && [ -f "requirements.txt" ]; then
        echo "📦 Installing Python dependencies from requirements.txt into .venv..."
        uv pip install --python "$TARGET_DIR/.venv/bin/python" -r requirements.txt
    fi
else
    echo "♻️  Resuming from filesystem snapshot: skipping git clone and package installation."
fi

# 4. Keep the sandbox alive for interaction via modal shell / ssh, or run the
#    OpenCode server when requested.
echo "🏝️  Sandbox Ready!"
if [ "${ENABLE_ANTIGRAVITY:-}" = "1" ]; then
    INSTANCE_NAME="${APP_NAME:-$(basename "$TARGET_DIR")-sandbox}"
    export PATH="/root/.local/bin:$PATH"
    echo "🏝️  Starting Antigravity Remote Control daemon ($INSTANCE_NAME)..."
    agy remote-control start --name "$INSTANCE_NAME" > /tmp/agy-remote-control.log 2>&1 || true
fi

if [ "${ENABLE_OPENCODE:-}" = "1" ]; then
    OPENCODE_PORT="${OPENCODE_PORT:-4096}"
    if [ -f /root/.config/opencode/opencode.env ]; then
        set -a
        source /root/.config/opencode/opencode.env
        set +a
    fi
    if [ -n "${OPENCODE_GO_API_KEY:-}" ]; then
        export OPENCODE_API_KEY="$OPENCODE_GO_API_KEY"
    fi
    echo "🏝️  Starting OpenCode server on port $OPENCODE_PORT..."
    nohup opencode serve --hostname 0.0.0.0 --port "$OPENCODE_PORT" > /tmp/opencode.log 2>&1 &
fi

if [ "${ENABLE_PI:-}" = "1" ]; then
    if [ -f /root/.config/opencode/opencode.env ]; then
        set -a
        source /root/.config/opencode/opencode.env
        set +a
    fi
    if [ -n "${OPENCODE_GO_API_KEY:-}" ]; then
        export OPENCODE_API_KEY="$OPENCODE_GO_API_KEY"
    fi
fi

if [ "${ENABLE_T3:-}" = "1" ]; then
    T3_PORT="${T3_PORT:-3775}"
    if [ -f "/opt/t3/t3" ]; then
        python3 -c '
import base64, os
p = "/opt/t3/t3"
t = base64.b64decode("ZnVuY3Rpb24gYnVpbGRBbnRpZ3Jhdml0eUFjcFNwYXduSW5wdXQoaW5wdXQpIHsKCXJldHVybiB7CgkJY29tbWFuZDogaW5wdXQuaW5zdGFsbGF0aW9uLmV4ZWN1dGFibGVQYXRoLAoJCWFyZ3M6IGlucHV0LnByb2ZpbGUucGxhdGZvcm0gPT09ICJsaW51eCIgPyBbIi0tdWlkPSJdIDogW10sCgkJY3dkOiBpbnB1dC5jd2QsCgkJZW52OiB7CgkJCS4uLmFudGlncmF2aXR5RW52aXJvbm1lbnQoaW5wdXQucHJvZmlsZSwgaW5wdXQuYmFzZUVudiA/PyBwcm9jZXNzLmVudiwgaW5wdXQuYXV0aCA/PyBBTlRJR1JBVklUWV9QRVJTT05BTF9BVVRILCBpbnB1dC5ydW50aW1lVGVtcERpcmVjdG9yeSksCgkJCUFOVElHUkFWSVRZX0hBUk5FU1NfUEFUSDogaW5wdXQuaW5zdGFsbGF0aW9uLmhhcm5lc3NQYXRoCgkJfSwKCQlleHRlbmRFbnY6IGZhbHNlCgl9Owp9")
r = base64.b64decode("ZnVuY3Rpb24gYnVpbGRBbnRpZ3Jhdml0eUFjcFNwYXduSW5wdXQoaW5wdXQpewpyZXR1cm57CmNvbW1hbmQ6aW5wdXQuaW5zdGFsbGF0aW9uLmV4ZWN1dGFibGVQYXRoLAphcmdzOiBpbnB1dC5wcm9maWxlLnBsYXRmb3JtPT09ImxpbnV4Ij9bIi0tZW5mb3JjZV9rZXJuZWxfaXB2Nl9zdXBwb3J0PWZhbHNlIiwiLS11aWQ9Il06W10sCmN3ZDppbnB1dC5jd2QsCmVudjp7Ci4uLmFudGlncmF2aXR5RW52aXJvbm1lbnQoaW5wdXQucHJvZmlsZSxpbnB1dC5iYXNlRW52Pz9wcm9jZXNzLmVudiwgaW5wdXQuYXV0aD8/QU5USUdSQVZJVFlfUEVSU09OQUxfQVVUSCwgaW5wdXQucnVudGltZVRlbXBEaXJlY3RvcnkpLApBTlRJR1JBVklUWV9IQVJORVNTX1BBVEg6aW5wdXQuaW5zdGFsbGF0aW9uLmhhcm5lc3NQYXRoCn0sCmV4dGVuZEVudjpmYWxzZQp9Owp9")
r_old = base64.b64decode("ZnVuY3Rpb24gYnVpbGRBbnRpZ3Jhdml0eUFjcFNwYXduSW5wdXQoaSl7cmV0dXJue2NvbW1hbmQ6aS5pbnN0YWxsYXRpb24uZXhlY3V0YWJsZVBhdGgsYXJnczppLnByb2ZpbGUucGxhdGZvcm09PT0ibGludXgiP1siLS1lbmZvcmNlX2tlcm5lbF9pcHY2X3N1cHBvcnQ9ZmFsc2UiLCItLXVpZD0iXTpbXSxjd2Q6aS5jd2Qs")
t_ssh = base64.b64decode("Y29uc3Qgc2hvcnRIb3N0bmFtZSA9ICh5aWVsZCogSG9zdG5hbWUpLnNwbGl0KCIuIilbMF0/LnRyaW0oKTsKCQkJaWYgKHNob3J0SG9zdG5hbWUgIT09IHZvaWQgMCAmJiBzaG9ydEhvc3RuYW1lLmxlbmd0aCA+IDApIHRhcmdldHMucHVzaCh7CgkJCQlraW5kOiAibWRucyIsCgkJCQlob3N0OiBgJHtzaG9ydEhvc3RuYW1lfS5sb2NhbGAsCgkJCQkuLi51c2VybmFtZSA9PT0gbnVsbCA/IHt9IDogeyB1c2VybmFtZSB9CgkJCX0pOwoJCQk=")
r_ssh = base64.b64decode("Y29uc3QgaCA9IHByb2Nlc3MuZW52LlQzX1NTSF9IT1NUfHwgcHJvY2Vzcy5lbnYuU0FOREJPWF9OQU1FOwoJCQljb25zdCBzID0gaCB8fCAoeWllbGQqIEhvc3RuYW1lKS5zcGxpdCgiLiIpWzBdPy50cmltKCk7CgkJCWlmIChzKSB0YXJnZXRzLnB1c2goewoJCQkJa2luZDogIm1kbnMiLAoJCQkJaG9zdDogaCB8fCBgJHtzfS5sb2NhbGAsCgkJCQkuLi51c2VybmFtZSA9PT0gbnVsbCA/IHt9IDogeyB1c2VybmFtZSB9CgkJCX0pOwoJCQk=")
try:
    with open(p, "rb") as f:
        c = f.read()
    new_c = c
    if t in new_c:
        new_c = new_c.replace(t, r, 1)
    elif r_old in new_c:
        pos = new_c.find(r_old)
        new_c = new_c[:pos] + r + new_c[pos+426:]
    if t_ssh in new_c:
        new_c = new_c.replace(t_ssh, r_ssh, 1)
    t_order = base64.b64decode("QlVJTFRfSU5fRFJJVkVSX09SREVSID0gWwoJCSJjb2RleCIsCgkJImNsYXVkZUFnZW50IiwKCQkiY3Vyc29yIiwKCQkiZ3JvayIsCgkJIm9wZW5jb2RlIiwKCQkiYW50aWdyYXZpdHkiLAoJCSJmeCIKCV07")
    r_order = base64.b64decode("QlVJTFRfSU5fRFJJVkVSX09SREVSID0gWwoJCSJjb2RleCIsCgkJImNsYXVkZUFnZW50IiwKCQkiY3Vyc29yIiwKCQkiZ3JvayIsCgkJImFudGlncmF2aXR5IiwKCQkib3BlbmNvZGUiLAoJCSJmeCIKCV07")
    t_cur = base64.b64decode("CQkiYW50aWdyYXZpdHkiOiBbCgkJCSJnZW1pbmktMy44LWZsYXNoLWhpZ2giLAoJCQkiZ2VtaW5pLTMuOC1mbGFzaC1tZWRpdW0iLAoJCQkiZ2VtaW5pLTMuOC1mbGFzaC1sb3ciCgkJXQ==")
    r_cur = base64.b64decode("CQkiYW50aWdyYXZpdHkiOiBbCgkJCSJnZW1pbmktMy44LWZsYXNoLWhpZ2giLyoKCQkJImdlbWluaS0zLjgtZmxhc2gtbWVkaXVtIiwKCQkJImdlbWluaS0zLjgtZmxhc2gtbG93IiovXQ==")
    t_mod = base64.b64decode("ImFudGlncmF2aXR5IjogewoJCQkiZGVmYXVsdHMiOiB7ICJjaGF0IjogImdlbWluaS0zLjgtZmxhc2gtaGlnaCIgfSwKCQkJInByb2ZpbGVzIjoge30sCgkJCSJtb2RlbHMiOiBbCgkJCQl7CgkJCQkJInNsdWciOiAiZ2VtaW5pLTMuOC1mbGFzaC1oaWdoIiwKCQkJCQkibmFtZSI6ICJHZW1pbmkgMy44IEZsYXNoIChIaWdoKSIsCgkJCQkJInN0YXR1cyI6ICJjdXJyZW50IgoJCQkJfSwKCQkJCXsKCQkJCQkic2x1ZyI6ICJnZW1pbmktMy44LWZsYXNoLW1lZGl1bSIsCgkJCQkJIm5hbWUiOiAiR2VtaW5pIDMuOCBGbGFzaCAoTWVkaXVtKSIsCgkJCQkJInN0YXR1cyI6ICJjdXJyZW50IgoJCQkJfSwKCQkJCXsKCQkJCQkic2x1ZyI6ICJnZW1pbmktMy44LWZsYXNoLWxvdyIsCgkJCQkJIm5hbWUiOiAiR2VtaW5pIDMuOCBGbGFzaCAoTG93KSIsCgkJCQkJInN0YXR1cyI6ICJjdXJyZW50IgoJCQkJfSwKCQkJCXsKCQkJCQkic2x1ZyI6ICJnZW1pbmktMy43LWZsYXNoLWhpZ2giLAoJCQkJCSJuYW1lIjogIkdlbWluaSAzLjcgRmxhc2ggKEhpZ2gpIiwKCQkJCQkic3RhdHVzIjogImxlZ2FjeSIKCQkJCX0sCgkJCQl7CgkJCQkJInNsdWciOiAiZ2VtaW5pLTMuNy1mbGFzaC1tZWRpdW0iLAoJCQkJCSJuYW1lIjogIkdlbWluaSAzLjcgRmxhc2ggKE1lZGl1bSkiLAoJCQkJCSJzdGF0dXMiOiAibGVnYWN5IgoJCQkJfSwKCQkJCXsKCQkJCQkic2x1ZyI6ICJnZW1pbmktMy43LWZsYXNoLWxvdyIsCgkJCQkJIm5hbWUiOiAiR2VtaW5pIDMuNyBGbGFzaCAoTG93KSIsCgkJCQkJInN0YXR1cyI6ICJsZWdhY3kiCgkJCQl9LAoJCQkJewoJCQkJCSJzbHVnIjogImdlbWluaS0zLjYtZmxhc2gtaGlnaCIsCgkJCQkJIm5hbWUiOiAiR2VtaW5pIDMuNiBGbGFzaCAoSGlnaCkiLAoJCQkJCSJzdGF0dXMiOiAibGVnYWN5IgoJCQkJfSwKCQkJCXsKCQkJCQkic2x1ZyI6ICJnZW1pbmktMy42LWZsYXNoLW1lZGl1bSIsCgkJCQkJIm5hbWUiOiAiR2VtaW5pIDMuNiBGbGFzaCAoTWVkaXVtKSIsCgkJCQkJInN0YXR1cyI6ICJsZWdhY3kiCgkJCQl9LAoJCQkJewoJCQkJCSJzbHVnIjogImdlbWluaS0zLjYtZmxhc2gtbG93IiwKCQkJCQkibmFtZSI6ICJHZW1pbmkgMy42IEZsYXNoIChMb3cpIiwKCQkJCQkic3RhdHVzIjogImxlZ2FjeSIKCQkJCX0sCgkJCQl7CgkJCQkJInNsdWciOiAiZ2VtaW5pLXByby1hZ2VudCIsCgkJCQkJIm5hbWUiOiAiR2VtaW5pIDMuMSBQcm8gKEhpZ2gpIiwKCQkJCQkic3RhdHVzIjogImxlZ2FjeSIKCQkJCX0sCgkJCQl7CgkJCQkJInNsdWciOiAiZ2VtaW5pLTMuMS1wcm8tbG93IiwKCQkJCQkibmFtZSI6ICJHZW1pbmkgMy4xIFBybyAoTG93KSIsCgkJCQkJInN0YXR1cyI6ICJsZWdhY3kiCgkJCQl9CgkJCV0=")
    r_mod = base64.b64decode("ImFudGlncmF2aXR5IjogewoJCQkiZGVmYXVsdHMiOiB7ICJjaGF0IjogImdlbWluaS0zLjgtZmxhc2gtaGlnaCIgfSwKCQkJInByb2ZpbGVzIjoge30sCgkJCSJtb2RlbHMiOiBbCgkJCQl7CgkJCQkJInNsdWciOiAiZ2VtaW5pLTMuOC1mbGFzaC1oaWdoIiwKCQkJCQkibmFtZSI6ICJHZW1pbmkgMy44IEZsYXNoIChIaWdoKSIsCgkJCQkJInN0YXR1cyI6ICJjdXJyZW50IgoJCQkJfS8qCQkJCXsKCQkJCQkic2x1ZyI6ICJnZW1pbmktMy44LWZsYXNoLW1lZGl1bSIsCgkJCQkJIm5hbWUiOiAiR2VtaW5pIDMuOCBGbGFzaCAoTWVkaXVtKSIsCgkJCQkJInN0YXR1cyI6ICJjdXJyZW50IgoJCQkJfSwKCQkJCXsKCQkJCQkic2x1ZyI6ICJnZW1pbmktMy44LWZsYXNoLWxvdyIsCgkJCQkJIm5hbWUiOiAiR2VtaW5pIDMuOCBGbGFzaCAoTG93KSIsCgkJCQkJInN0YXR1cyI6ICJjdXJyZW50IgoJCQkJfSwKCQkJCXsKCQkJCQkic2x1ZyI6ICJnZW1pbmktMy43LWZsYXNoLWhpZ2giLAoJCQkJCSJuYW1lIjogIkdlbWluaSAzLjcgRmxhc2ggKEhpZ2gpIiwKCQkJCQkic3RhdHVzIjogImxlZ2FjeSIKCQkJCX0sCgkJCQl7CgkJCQkJInNsdWciOiAiZ2VtaW5pLTMuNy1mbGFzaC1tZWRpdW0iLAoJCQkJCSJuYW1lIjogIkdlbWluaSAzLjcgRmxhc2ggKE1lZGl1bSkiLAoJCQkJCSJzdGF0dXMiOiAibGVnYWN5IgoJCQkJfSwKCQkJCXsKCQkJCQkic2x1ZyI6ICJnZW1pbmktMy43LWZsYXNoLWxvdyIsCgkJCQkJIm5hbWUiOiAiR2VtaW5pIDMuNyBGbGFzaCAoTG93KSIsCgkJCQkJInN0YXR1cyI6ICJsZWdhY3kiCgkJCQl9LAoJCQkJewoJCQkJCSJzbHVnIjogImdlbWluaS0zLjYtZmxhc2gtaGlnaCIsCgkJCQkJIm5hbWUiOiAiR2VtaW5pIDMuNiBGbGFzaCAoSGlnaCkiLAoJCQkJCSJzdGF0dXMiOiAibGVnYWN5IgoJCQkJfSwKCQkJCXsKCQkJCQkic2x1ZyI6ICJnZW1pbmktMy42LWZsYXNoLW1lZGl1bSIsCgkJCQkJIm5hbWUiOiAiR2VtaW5pIDMuNiBGbGFzaCAoTWVkaXVtKSIsCgkJCQkJInN0YXR1cyI6ICJsZWdhY3kiCgkJCQl9LAoJCQkJewoJCQkJCSJzbHVnIjogImdlbWluaS0zLjYtZmxhc2gtbG93IiwKCQkJCQkibmFtZSI6ICJHZW1pbmkgMy42IEZsYXNoIChMb3cpIiwKCQkJCQkic3RhdHVzIjogImxlZ2FjeSIKCQkJCX0sCgkJCQl7CgkJCQkJInNsdWciOiAiZ2VtaW5pLXByby1hZ2VudCIsCgkJCQkJIm5hbWUiOiAiR2VtaW5pIDMuMSBQcm8gKEhpZ2gpIiwKCQkJCQkic3RhdHVzIjogImxlZ2FjeSIKCQkJCX0sCgkJCQl7CgkJCQkJInNsdWciOiAiZ2VtaW5pLTMuMS1wcm8tbG93IiwKCQkJCQkibmFtZSI6ICJHZW1pbmkgMy4xIFBybyAoTG93KSIsCgkJCQkJInN0YXR1cyI6ICJsZWdhY3kiCgkJCSovCgkJCV0=")
    if t_order in new_c:
        new_c = new_c.replace(t_order, r_order, 1)
    if t_cur in new_c:
        new_c = new_c.replace(t_cur, r_cur, 1)
    if t_mod in new_c:
        new_c = new_c.replace(t_mod, r_mod, 1)
    if new_c != c:
        with open(p + ".tmp", "wb") as f:
            f.write(new_c)
        os.chmod(p + ".tmp", 0o755)
        os.replace(p + ".tmp", p)
except Exception:
    pass
' 2>/dev/null || true
    fi

    if [ -f /root/.config/opencode/opencode.env ]; then
        set -a
        source /root/.config/opencode/opencode.env
        set +a
    fi
    if [ -n "${OPENCODE_GO_API_KEY:-}" ]; then
        export OPENCODE_API_KEY="$OPENCODE_GO_API_KEY"
    fi

    # Pre-authenticate Antigravity and OpenCode providers in T3 Code
    python3 -c '
import hashlib, json, os

accounts = [
    ("antigravity", "Antigravity", os.path.expanduser("~/.gemini/antigravity-cli/profiles/m47"), True),
    ("antigravity-anv", "Antigravity (ANV)", os.path.expanduser("~/.gemini/antigravity-cli/profiles/anv"), False),
    ("antigravity-mgh", "Antigravity (MGH)", os.path.expanduser("~/.gemini/antigravity-cli/profiles/mgh"), False),
]

t3_settings_path = "/root/.t3/userdata/settings.json"
os.makedirs(os.path.dirname(t3_settings_path), mode=0o755, exist_ok=True)
settings = {}
if os.path.exists(t3_settings_path):
    try:
        with open(t3_settings_path, "r") as fp:
            settings = json.load(fp)
    except Exception:
        settings = {}
if "providerInstances" not in settings:
    settings["providerInstances"] = {}

t3_cache_dir = "/root/.t3/caches"
os.makedirs(t3_cache_dir, mode=0o755, exist_ok=True)

configured_antigravity = []
for instance_id, display_name, token_path, is_primary in accounts:
    if not os.path.exists(token_path) and is_primary:
        token_path = os.path.expanduser("~/.gemini/antigravity-cli/antigravity-oauth-token")

    if not os.path.exists(token_path):
        continue

    try:
        with open(token_path, "r") as f:
            data = json.load(f)
        refresh_token = data.get("token", {}).get("refresh_token") or data.get("refresh_token")
        if not refresh_token:
            continue

        acp_token = {
            "client_id": os.environ.get("ANTIGRAVITY_CLIENT_ID") or os.environ.get("GOOGLE_CLIENT_ID", "dummy-client-id.apps.googleusercontent.com"),
            "client_secret": os.environ.get("ANTIGRAVITY_CLIENT_SECRET") or os.environ.get("GOOGLE_CLIENT_SECRET", "dummy-client-secret"),
            "refresh_token": refresh_token,
            "token_uri": "https://oauth2.googleapis.com/token",
            "scopes": [
                "https://www.googleapis.com/auth/cloud-platform",
                "https://www.googleapis.com/auth/userinfo.email",
                "https://www.googleapis.com/auth/aicode"
            ]
        }
        acp_settings = {"auth": {"type": "oauth-personal"}}
        t3_hash = hashlib.sha256(instance_id.encode("utf-8")).hexdigest()
        target_dirs = [f"/root/.t3/userdata/providers/antigravity/{t3_hash}/antigravity-acp"]
        if is_primary:
            target_dirs.append(os.path.expanduser("~/.gemini/antigravity-acp"))

        for d in target_dirs:
            os.makedirs(d, mode=0o700, exist_ok=True)
            tok_file = os.path.join(d, "acp_token.json")
            set_file = os.path.join(d, "settings.json")
            with open(tok_file, "w") as fp:
                json.dump(acp_token, fp, indent=2)
            os.chmod(tok_file, 0o600)
            with open(set_file, "w") as fp:
                json.dump(acp_settings, fp, indent=2)
            os.chmod(set_file, 0o600)

        settings["providerInstances"][instance_id] = {
            "driver": "antigravity",
            "displayName": display_name,
            "enabled": True
        }
        configured_antigravity.append(instance_id)

        t3_cache_file = os.path.join(t3_cache_dir, f"{instance_id}.json")
        cache_data = {
            "displayName": display_name,
            "showInteractionModeToggle": False,
            "enabled": True,
            "installed": True,
            "version": "1.3.0",
            "status": "ready",
            "auth": {
                "status": "authenticated",
                "type": "oauth-personal",
                "label": "Google account"
            },
            "setup": {
                "canAuthenticate": True,
                "canInstall": True
            },
            "checkedAt": "2026-10-27T12:00:00.000Z",
            "models": [
                {
                    "slug": "gemini-3.8-flash-high",
                    "name": "Gemini 3.8 Flash (High)",
                    "isCustom": False,
                    "isDefault": True,
                    "aliases": [f"{instance_id}-default"],
                    "capabilities": {"optionDescriptors": []}
                }
            ],
            "slashCommands": [],
            "skills": [],
            "supportsConversationRollback": False,
            "supportsTextGeneration": True,
            "instanceId": instance_id,
            "driver": "antigravity"
        }
        with open(t3_cache_file, "w") as fp:
            json.dump(cache_data, fp, indent=2)
        os.chmod(t3_cache_file, 0o644)
    except Exception as e:
        print(f"Warning: Failed to setup Antigravity ACP credentials for {instance_id}: {e}")

# 2. OpenCode Provider
opencode_env_path = "/root/.config/opencode/opencode.env"
has_opencode_key = bool(os.environ.get("OPENCODE_GO_API_KEY"))
if not has_opencode_key and os.path.exists(opencode_env_path):
    try:
        with open(opencode_env_path, "r") as ef:
            for eline in ef:
                if eline.startswith("OPENCODE_GO_API_KEY="):
                    val = eline.split("=", 1)[1].strip().strip("\"").strip(chr(39))
                    if val:
                        has_opencode_key = True
                        break
    except Exception:
        pass

if has_opencode_key:
    if "opencode" not in settings["providerInstances"]:
        settings["providerInstances"]["opencode"] = {
            "driver": "opencode",
            "displayName": "OpenCode",
            "enabled": True,
            "binaryPath": "/root/.opencode/bin/opencode"
        }
    else:
        settings["providerInstances"]["opencode"]["enabled"] = True
        settings["providerInstances"]["opencode"]["binaryPath"] = "/root/.opencode/bin/opencode"
    print("✨ Pre-configured OpenCode provider in T3 Code")

if "claudeAgent" not in settings["providerInstances"]:
    settings["providerInstances"]["claudeAgent"] = {
        "driver": "claudeAgent",
        "enabled": False
    }
if "codex" not in settings["providerInstances"]:
    settings["providerInstances"]["codex"] = {
        "driver": "codex",
        "enabled": False
    }

default_agy_instance = None
for candidate in ["antigravity-anv", "antigravity-mgh", "antigravity"]:
    if candidate in configured_antigravity:
        default_agy_instance = candidate
        break
if default_agy_instance is None and configured_antigravity:
    default_agy_instance = configured_antigravity[0]

if default_agy_instance:
    model_sel = {
        "instanceId": default_agy_instance,
        "model": "gemini-3.8-flash-low"
    }
    if not settings.get("sourceControlWriterModelSelection") or settings.get("sourceControlWriterModelSelection", {}).get("instanceId") == "codex":
        settings["sourceControlWriterModelSelection"] = model_sel
    if not settings.get("textGenerationModelSelection") or settings.get("textGenerationModelSelection", {}).get("instanceId") == "codex":
        settings["textGenerationModelSelection"] = model_sel

with open(t3_settings_path, "w") as fp:
    json.dump(settings, fp, indent=2)
os.chmod(t3_settings_path, 0o644)
print("✨ Pre-authenticated Antigravity providers in T3 Code")
' 2>/dev/null || true

    # Install T3 CLI wrapper that ensures t3 pair uses the Modal HTTPS public URL
    cat << 'EOF' > /usr/local/bin/t3.wrapper
#!/usr/bin/env bash
REAL_T3="/opt/t3/t3"

if [ "${1:-}" = "pair" ]; then
    PUBLIC_URL="${T3_PUBLIC_URL:-}"
    if [ -z "$PUBLIC_URL" ] && [ -f "/root/.t3/public_url" ]; then
        PUBLIC_URL=$(cat /root/.t3/public_url 2>/dev/null | tr -d '\r\n')
    fi

    if [ -n "$PUBLIC_URL" ]; then
        python3 -c "
import json, os, sys

url = sys.argv[1]
candidates = [
    '/root/.t3/userdata/server-runtime.json',
    '/root/.t3/dev/server-runtime.json',
]

for p in candidates:
    if os.path.isfile(p):
        try:
            with open(p, 'r') as f:
                d = json.load(f)
            if d.get('devUrl') != url:
                d['devUrl'] = url
                tmp = p + '.tmp'
                with open(tmp, 'w') as f:
                    json.dump(d, f, indent=2)
                os.replace(tmp, p)
        except Exception:
            pass
" "$PUBLIC_URL" 2>/dev/null || true
    fi

    has_base_dir=0
    for arg in "$@"; do
        if [ "$arg" = "--base-dir" ] || [[ "$arg" == --base-dir=* ]]; then
            has_base_dir=1
            break
        fi
    done

    if [ "$has_base_dir" -eq 0 ]; then
        if [ ! -f ".t3/userdata/server-runtime.json" ] && [ -f "/root/.t3/userdata/server-runtime.json" ]; then
            set -- "$@" --base-dir /root/.t3
        fi
    fi
fi

exec "$REAL_T3" "$@"
EOF
    chmod +x /usr/local/bin/t3.wrapper
    mv -f /usr/local/bin/t3.wrapper /usr/local/bin/t3

    echo "PRETTY_HOSTNAME=\"${T3_SSH_HOST:-${SANDBOX_NAME:-$APP_NAME}}\"" > /etc/machine-info 2>/dev/null || true

    echo "🏝️  Starting T3 Code server on port $T3_PORT..."
    nohup t3 serve --host 0.0.0.0 --port "$T3_PORT" --mode web --auto-bootstrap-project-from-cwd "$TARGET_DIR" > /tmp/t3.log 2>&1 &
    t3 auth pairing create --ttl 24h --json > /tmp/t3-pairing.json 2>/dev/null || true
fi
exec sleep infinity
