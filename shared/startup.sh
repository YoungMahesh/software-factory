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

    # Initially stop the service until the target web port actually opens
    /etc/init.d/cloudflared stop >/dev/null 2>&1 || true

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
        if [ -f "/root/secrets/org/token" ]; then
            echo "🔐 Decrypting organization token from /root/secrets/org/token..."
            GH_TOKEN=$(SOPS_AGE_KEY="$AGE_PRIVATE_KEY" sops decrypt "/root/secrets/org/token" 2>/dev/null | tr -d '\r\n' || true)
            rm -f /root/secrets/org/token
            export ORG_TOKEN="1"
            export TRACKER="${TRACKER:-github}"
        elif [ -f "/root/secrets/repo/fetch.env" ] || [ -f "/root/secrets/fetch.env" ]; then
            FETCH_SECRET_FILE="/root/secrets/repo/fetch.env"
            [ ! -f "$FETCH_SECRET_FILE" ] && FETCH_SECRET_FILE="/root/secrets/fetch.env"
            echo "🔐 Decrypting repository fetch secret from $FETCH_SECRET_FILE..."
            DECRYPTED_FETCH=$(SOPS_AGE_KEY="$AGE_PRIVATE_KEY" sops decrypt "$FETCH_SECRET_FILE" 2>/dev/null || true)
            if [ -n "$DECRYPTED_FETCH" ]; then
                while IFS= read -r line || [ -n "$line" ]; do
                    [[ "$line" =~ ^[[:space:]]*# ]] && continue
                    [[ -z "${line// }" ]] && continue
                    if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
                        var_name="${BASH_REMATCH[1]}"
                        var_val="${BASH_REMATCH[2]}"
                        if [[ "$var_val" =~ ^\"(.*)\"$ ]] || [[ "$var_val" =~ ^\'(.*)\'$ ]]; then
                            var_val="${BASH_REMATCH[1]}"
                        fi
                        export "$var_name"="$var_val"
                    fi
                done <<< "$DECRYPTED_FETCH"
            fi
            rm -f "$FETCH_SECRET_FILE"
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
    echo "📂 Workspace resolved to $TARGET_DIR"
    cd "$TARGET_DIR"
else
    if [ "${NO_REPO:-0}" = "1" ]; then
        echo "🏝️  No repository secret provided: skipping repository fetch."
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
        echo "📂 Workspace resolved to $TARGET_DIR"
    else
        if [ -z "${AGE_PRIVATE_KEY:-}" ]; then
            echo "ERROR: AGE_PRIVATE_KEY is not set in the environment. Ensure the Modal secret 'share0' is configured with AGE_PRIVATE_KEY." >&2
            exit 1
        fi

        if [ -f "/root/secrets/org/token" ]; then
            if [ -z "${GH_REPO:-}" ]; then
                echo "ERROR: GH_REPO environment variable is required when using organization credentials." >&2
                exit 1
            fi
            echo "🔐 Decrypting organization token from /root/secrets/org/token..."
            GH_TOKEN=$(SOPS_AGE_KEY="$AGE_PRIVATE_KEY" sops decrypt "/root/secrets/org/token" 2>/dev/null | tr -d '\r\n')
            if [ -z "$GH_TOKEN" ]; then
                echo "ERROR: Failed to decrypt organization token using AGE_PRIVATE_KEY." >&2
                rm -rf /root/secrets/org
                exit 1
            fi
            rm -f /root/secrets/org/token
            echo "🧹 Purged encrypted organization token from disk."
            export ORG_TOKEN="1"
            export TRACKER="${TRACKER:-github}"
        elif [ -f "/root/secrets/repo/fetch.env" ] || [ -f "/root/secrets/fetch.env" ]; then
            FETCH_SECRET_FILE=""
            if [ -f "/root/secrets/repo/fetch.env" ]; then
                FETCH_SECRET_FILE="/root/secrets/repo/fetch.env"
            else
                FETCH_SECRET_FILE="/root/secrets/fetch.env"
            fi

            echo "🔐 Decrypting repository fetch secret from $FETCH_SECRET_FILE..."
            DECRYPTED_FETCH=$(SOPS_AGE_KEY="$AGE_PRIVATE_KEY" sops decrypt "$FETCH_SECRET_FILE" 2>/dev/null || true)
            if [ -z "$DECRYPTED_FETCH" ]; then
                echo "ERROR: Failed to decrypt $FETCH_SECRET_FILE using AGE_PRIVATE_KEY." >&2
                rm -rf /root/secrets/repo
                exit 1
            fi

            while IFS= read -r line || [ -n "$line" ]; do
                [[ "$line" =~ ^[[:space:]]*# ]] && continue
                [[ -z "${line// }" ]] && continue
                if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
                    var_name="${BASH_REMATCH[1]}"
                    var_val="${BASH_REMATCH[2]}"
                    if [[ "$var_val" =~ ^\"(.*)\"$ ]] || [[ "$var_val" =~ ^\'(.*)\'$ ]]; then
                        var_val="${BASH_REMATCH[1]}"
                    fi
                    export "$var_name"="$var_val"
                fi
            done <<< "$DECRYPTED_FETCH"

            rm -f "$FETCH_SECRET_FILE"
            echo "🧹 Purged encrypted fetch secret ($FETCH_SECRET_FILE) from disk."
        else
            echo "ERROR: Repository secret not found (expected /root/secrets/org/token or /root/secrets/repo/fetch.env)." >&2
            exit 1
        fi

        if [ -z "${GH_REPO:-}" ]; then
            echo "ERROR: GH_REPO is not set." >&2
            exit 1
        fi

        if [ -z "${GH_TOKEN:-}" ]; then
            echo "ERROR: GH_TOKEN is not set." >&2
            exit 1
        fi

        REPO_NAME=$(basename "$GH_REPO")
        TARGET_DIR="/root/$REPO_NAME"

        if [ ! -d "$TARGET_DIR" ]; then
            echo "🏝️  Cloning $GH_REPO (branch: $BRANCH)..."
            GIT_ASKPASS=echo git clone --quiet --depth 50 --branch "$BRANCH" --single-branch \
                "https://oauth2:${GH_TOKEN}@github.com/${GH_REPO}.git" "$TARGET_DIR"
        fi

        cd "$TARGET_DIR"

        if ! git symbolic-ref -q HEAD >/dev/null; then
            echo "ERROR: '$BRANCH' resolved to a tag or detached commit. Only Git branches are supported." >&2
            exit 1
        fi
    fi
fi

# Decrypt repository environment secrets if env.map is present
ENV_MAP_FILE="/root/secrets/repo/env.map"
if [ -f "$ENV_MAP_FILE" ]; then
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

            src_file="/root/secrets/repo/$src_rel"
            dest_file="$TARGET_DIR/$dest_rel"

            if [ ! -f "$src_file" ]; then
                echo "ERROR: Mapped repository secret file not found at $src_file." >&2
                rm -rf /root/secrets/repo
                exit 1
            fi

            mkdir -p "$(dirname "$dest_file")"
            if ! SOPS_AGE_KEY="$AGE_PRIVATE_KEY" sops decrypt "$src_file" > "$dest_file"; then
                echo "ERROR: Failed to decrypt $src_file using AGE_PRIVATE_KEY." >&2
                rm -f "$dest_file"
                rm -rf /root/secrets/repo
                exit 1
            fi
            chmod 600 "$dest_file"
            echo "   • Decrypted $src_rel -> $dest_rel"
        fi
    done < "$ENV_MAP_FILE"
fi

if [ -d /root/secrets/repo ]; then
    rm -rf /root/secrets/repo
    echo "🧹 Purged repository secrets staging directory (/root/secrets/repo)."
fi

if [ -d /root/secrets/org ]; then
    rm -rf /root/secrets/org
    echo "🧹 Purged organization secrets staging directory (/root/secrets/org)."
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
echo "=== T3 Code Process ===" && ps aux | grep [t]3
echo "=== T3 Server Log ===" && tail -n 20 /tmp/t3.log 2>/dev/null || true
echo "=== Listening Sockets ===" && (ss -tulpn 2>/dev/null | grep 3775 || netstat -tulpn 2>/dev/null | grep 3775 || true)
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

if [ "${ENABLE_ANTIGRAVITY:-}" = "1" ] || [ "${ENABLE_MODAL:-}" = "1" ] || [ "${ENABLE_OPENCODE:-}" = "1" ] || [ "${ENABLE_SOPS:-}" = "1" ]; then
    if [ "${RESUME_SNAPSHOT:-0}" != "1" ]; then
        if [ -z "${AGE_PRIVATE_KEY:-}" ]; then
            echo "ERROR: Credentials decryption requested (--agy, --modal, --opencode, or --sops), but AGE_PRIVATE_KEY is not set in the environment. Ensure the Modal secret 'share0' is configured with AGE_PRIVATE_KEY." >&2
            exit 1
        fi

        mkdir -p ~/.config/sops/age
        echo "$AGE_PRIVATE_KEY" > ~/.config/sops/age/keys.txt
        chmod 600 ~/.config/sops/age/keys.txt

        setup_args=()
        if [ "${ENABLE_MODAL:-}" = "1" ]; then
            setup_args+=("--modal")
        fi
        if [ "${ENABLE_ANTIGRAVITY:-}" = "1" ]; then
            setup_args+=("--agy")
        fi
        if [ "${ENABLE_OPENCODE:-}" = "1" ]; then
            setup_args+=("--opencode")
        fi

        setup_status=0
        if [ ${#setup_args[@]} -gt 0 ] && [ -f "/root/scripts/setup.sh" ]; then
            echo "🔐 Decrypting tooling credentials with SOPS..."
            bash /root/scripts/setup.sh "${setup_args[@]}" || setup_status=$?
        fi
    fi
fi

# Scrub staged encrypted tooling secrets immediately after decryption
rm -f /root/secrets/opencode.env /root/secrets/antigravity-oauth-token.json /root/secrets/modal.toml

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

# Unconditionally scrub GH_TOKEN and ephemeral repository credentials from memory
grep -qxF "unset GH_TOKEN" ~/.bashrc 2>/dev/null || echo "unset GH_TOKEN" >> ~/.bashrc
grep -qxF "unset DOTENV_PRIVATE_KEY" ~/.bashrc 2>/dev/null || echo "unset DOTENV_PRIVATE_KEY" >> ~/.bashrc
unset GH_TOKEN
unset DOTENV_PRIVATE_KEY
unset DECRYPTED_FETCH

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

if [ "${ENABLE_T3:-}" = "1" ]; then
    T3_PORT="${T3_PORT:-3775}"
    echo "🏝️  Starting T3 Code server on port $T3_PORT..."
    nohup t3 serve --host 0.0.0.0 --port "$T3_PORT" --mode web --auto-bootstrap-project-from-cwd "$TARGET_DIR" > /tmp/t3.log 2>&1 &
    t3 auth pairing create --ttl 24h --json > /tmp/t3-pairing.json 2>/dev/null || true
fi
exec sleep infinity
