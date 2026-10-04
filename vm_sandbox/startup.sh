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

# Start Docker daemon in background
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

# make fnm path available to shell (logs of fnm-installation mention this path)
FNM_PATH="/root/.local/share/fnm"
export PATH="$FNM_PATH:$PATH"
eval "$(fnm env --shell bash)"
# Download and install Node.js:
fnm install 24
node -v
npm -v
corepack enable pnpm
corepack prepare pnpm@10.31.0 --activate


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
grep -qxF 'export PATH="/root/.local/share/fnm:$PATH"' ~/.bashrc 2>/dev/null || echo 'export PATH="/root/.local/share/fnm:$PATH"' >> ~/.bashrc
grep -qxF 'eval "$(fnm env --shell bash)"' ~/.bashrc 2>/dev/null || echo 'eval "$(fnm env --shell bash)"' >> ~/.bashrc

if [ "${ENABLE_OPENCODE:-}" = "1" ]; then
    grep -qxF 'export PATH="/root/.opencode/bin:$PATH"' ~/.bashrc 2>/dev/null || echo 'export PATH="/root/.opencode/bin:$PATH"' >> ~/.bashrc
fi
if [ "${ENABLE_ANTIGRAVITY:-}" = "1" ]; then
    grep -qxF 'export PATH="/root/.local/bin:$PATH"' ~/.bashrc 2>/dev/null || echo 'export PATH="/root/.local/bin:$PATH"' >> ~/.bashrc
fi

if [ "${ENABLE_MODAL:-}" = "1" ]; then
    VENV_DIR="$TARGET_DIR/.venv"
    if [ ! -d "$VENV_DIR" ]; then
        echo "⚡ Creating virtual environment at $VENV_DIR..."
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

    echo "⚡ Installing Modal client package into .venv..."
    "$VENV_DIR/bin/pip" install --quiet modal

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

# 2. Decrypt / write environment keys if provided
if [ -n "${DOTENV_PRIVATE_KEY:-}" ]; then
    echo "DOTENV_PRIVATE_KEY=$DOTENV_PRIVATE_KEY" > .env.keys
fi

if [ "${ENABLE_ANTIGRAVITY:-}" = "1" ] || [ "${ENABLE_MODAL:-}" = "1" ]; then
    if [ -z "${AGE_PRIVATE_KEY:-}" ]; then
        echo "ERROR: Credentials decryption requested (--agy or --modal), but AGE_PRIVATE_KEY is not set in the environment." >&2
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

    setup_status=0
    if [ -f "scripts/setup.sh" ]; then
        echo "🔐 Decrypting secrets with SOPS..."
        bash scripts/setup.sh "${setup_args[@]}" || setup_status=$?
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

# Allocate swap space: 2× the VM RAM (SWAP_GB is exported by main.py)
SWAP_GB="${SWAP_GB:-2}"
if ! swapon --show | grep -q '/swapfile'; then
    fallocate -l "${SWAP_GB}G" /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=$((SWAP_GB * 1024))
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
fi

# 3. Install dependencies if package manifest exists
if [ -f "pnpm-lock.yaml" ]; then
    pnpm install
elif [ -f "package.json" ]; then
    npm install
fi

if [ "${ENABLE_MODAL:-}" = "1" ] && [ -f "requirements.txt" ]; then
    echo "📦 Installing Python dependencies from requirements.txt into .venv..."
    "$TARGET_DIR/.venv/bin/pip" install -r requirements.txt
fi


# 4. Keep sandbox alive for interaction via modal shell / ssh, or run the
#    OpenCode server as a background process when requested.
echo "🏝️  Sandbox Ready!"
if [ "${ENABLE_OPENCODE:-}" = "1" ]; then
    OPENCODE_PORT="${OPENCODE_PORT:-4096}"
    echo "🏝️  Starting OpenCode server on port $OPENCODE_PORT..."
    (cd /root && nohup opencode serve --hostname=0.0.0.0 --port="$OPENCODE_PORT" --log-level=DEBUG --print-logs > /tmp/opencode.log 2>&1 &)
fi
exec sleep infinity
