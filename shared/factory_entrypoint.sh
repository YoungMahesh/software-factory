#!/usr/bin/env bash
set -euo pipefail

FEATURE_SLUG=""
ISSUE_ID=""
MODEL_ID=""
TRACKER="${TRACKER:-}"

DEV_PREVIEW="${DEV_PREVIEW:-0}"

PREVIEW_ONLY="${PREVIEW_ONLY:-0}"
TARGET_BRANCH="${BRANCH:-}"

# Parse command line arguments (supporting both flags and positional fallbacks)
while [[ $# -gt 0 ]]; do
    case "$1" in
        --feature|-f)
            FEATURE_SLUG="$2"
            shift 2
            ;;
        --issue|-i)
            ISSUE_ID="$2"
            shift 2
            ;;
        --model|-m)
            MODEL_ID="$2"
            shift 2
            ;;
        --tracker|-t)
            TRACKER="$2"
            shift 2
            ;;
        --branch|-b)
            TARGET_BRANCH="$2"
            shift 2
            ;;
        --preview-only)
            PREVIEW_ONLY="1"
            DEV_PREVIEW="1"
            shift
            ;;
        --dev|--preview)
            DEV_PREVIEW="1"
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--feature <slug>] [--issue <id>] [--model <model>] [--tracker <github|local>] [--branch <branch>] [--dev] [--preview-only]"
            exit 0
            ;;
        *)
            if [ -z "$FEATURE_SLUG" ]; then
                FEATURE_SLUG="$1"
            elif [ -z "$ISSUE_ID" ]; then
                ISSUE_ID="$1"
            elif [ -z "$MODEL_ID" ]; then
                MODEL_ID="$1"
            fi
            shift
            ;;
    esac
done

FEATURE_SLUG="${FEATURE_SLUG:-${FEATURE_SLUG_ENV:-${FEATURE:-}}}"

if [ -z "$FEATURE_SLUG" ] && [ -n "$ISSUE_ID" ]; then
    FEATURE_SLUG="issue-${ISSUE_ID}"
fi

if [ -z "$FEATURE_SLUG" ]; then
    if [ "${PREVIEW_ONLY:-0}" = "1" ]; then
        FEATURE_SLUG="${TARGET_BRANCH:-preview}"
    else
        echo "ERROR: Feature slug is required (--feature <slug> or positional argument, or --issue <id>)." >&2
        exit 1
    fi
fi

echo "================================================================"
echo "🏭 Modal Software Factory Container Entrypoint"
echo "  • Feature: ${FEATURE_SLUG}"
if [ -n "$ISSUE_ID" ]; then
    echo "  • Target Issue: ${ISSUE_ID}"
else
    echo "  • Execution Mode: Autonomous Feature Batch"
fi
if [ -n "$MODEL_ID" ]; then
    echo "  • Model Override: ${MODEL_ID}"
fi
if [ "${DEV_PREVIEW:-0}" = "1" ]; then
    echo "  • Dev Preview: Enabled (port 3000 -> https://3000.mahesh0.dev)"
fi
echo "================================================================"

BASE_DIR="${SANDBOX_ROOT:-/root}"

# Start Docker daemon in background if enabled (VM Sandbox)
if [ "${ENABLE_DOCKER:-}" = "1" ]; then
    echo "🐳 Starting dockerd for VM Sandbox..."
    /usr/bin/dockerd > /var/log/dockerd.log 2>&1 &
    for i in $(seq 1 30); do
        if [ -S /var/run/docker.sock ] && docker info >/dev/null 2>&1; then
            echo "🐳 Docker daemon is ready!"
            break
        fi
        if [ "$i" -eq 30 ]; then
            echo "ERROR: dockerd failed to start within 30s. Logs:" >&2
            cat /var/log/dockerd.log >&2 || true
            exit 1
        fi
        sleep 1
    done
fi

# Allocate swap space if requested (VM Sandbox)
if [ -n "${SWAP_GB:-}" ] && [ "$SWAP_GB" -gt 0 ] 2>/dev/null; then
    if ! swapon --show | grep -q '/swapfile'; then
        echo "💾 Allocating ${SWAP_GB} GB swapfile..."
        fallocate -l "${SWAP_GB}G" /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=$((SWAP_GB * 1024))
        chmod 600 /swapfile
        mkswap /swapfile
        swapon /swapfile
    fi
fi

# 1. SOPS Age key bootstrap
if [ -z "${AGE_PRIVATE_KEY:-}" ]; then
    echo "ERROR: AGE_PRIVATE_KEY is not set in the environment. Ensure the Modal secret 'share0' is mounted." >&2
    exit 1
fi

mkdir -p ~/.config/sops/age
echo "$AGE_PRIVATE_KEY" > ~/.config/sops/age/keys.txt
chmod 600 ~/.config/sops/age/keys.txt
export SOPS_AGE_KEY="$AGE_PRIVATE_KEY"
export SOPS_AGE_KEY_FILE="${HOME:-/root}/.config/sops/age/keys.txt"

# Start Cloudflare Tunnel service and port watcher if enabled or in dev preview mode
WATCHER_PID=""
if [ "${ENABLE_CLOUDFLARE:-0}" != "0" ] || [ "${DEV_PREVIEW:-0}" = "1" ]; then
    CLOUDFLARE_SECRET_FILE="${BASE_DIR}/secrets/cloudflare.env"
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
        cloudflared service install "$CF_TOKEN" 2>/dev/null || true
    elif [ -f /etc/cloudflared/token ]; then
        CURRENT_TOKEN=$(cat /etc/cloudflared/token 2>/dev/null || true)
        if [ "$CURRENT_TOKEN" != "$CF_TOKEN" ]; then
            echo "$CF_TOKEN" > /etc/cloudflared/token
        fi
    fi

    /etc/init.d/cloudflared stop >/dev/null 2>&1 || true

    WATCHER_BIN="/usr/local/bin/cloudflared-port-watcher"
    if [ ! -f "$WATCHER_BIN" ]; then
        mkdir -p "$(dirname "$WATCHER_BIN")" 2>/dev/null || true
        cat << 'EOF' > "$WATCHER_BIN" 2>/dev/null || true
#!/usr/bin/env bash
TARGET_PORT="${1:-3000}"
CHECK_INTERVAL=2

while true; do
    TARGET_HEX=$(printf "%04X" "$TARGET_PORT")
    if grep -q -E ":${TARGET_HEX} [0-9A-F:]+ 0A" /proc/net/tcp /proc/net/tcp6 2>/dev/null; then
        if ! /etc/init.d/cloudflared status >/dev/null 2>&1; then
            echo "[$(date +%T)] 🚇 Port $TARGET_PORT is active. Starting Cloudflare Tunnel..."
            /etc/init.d/cloudflared start >/dev/null 2>&1 || true
        fi
    else
        if /etc/init.d/cloudflared status >/dev/null 2>&1; then
            echo "[$(date +%T)] 🚇 Port $TARGET_PORT is closed. Stopping Cloudflare Tunnel..."
            /etc/init.d/cloudflared stop >/dev/null 2>&1 || true
        fi
    fi
    sleep "$CHECK_INTERVAL"
done
EOF
        chmod +x "$WATCHER_BIN" 2>/dev/null || true
    fi

    if [ -x "$WATCHER_BIN" ]; then
        nohup "$WATCHER_BIN" "${PORT:-3000}" > /var/log/cloudflared-watcher.log 2>&1 &
        WATCHER_PID=$!
        echo "🚇 Cloudflare Tunnel port watcher started for port ${PORT:-3000} (PID: $WATCHER_PID)."
    fi
    rm -f "$CLOUDFLARE_SECRET_FILE"
fi

# 2. Ephemerally decrypt OpenCode credentials into ~/.config/opencode/opencode.env
OPENCODE_SECRET_FILE="${BASE_DIR}/secrets/opencode.env"
if [ -f "$OPENCODE_SECRET_FILE" ]; then
    echo "🔑 Decrypting OpenCode credentials via Tooling Setup Script..."
    if [ -f "${BASE_DIR}/scripts/setup.sh" ]; then
        SOPS_AGE_KEY="$AGE_PRIVATE_KEY" bash "${BASE_DIR}/scripts/setup.sh" --opencode
    else
        mkdir -p "${BASE_DIR}/.config/opencode"
        SOPS_AGE_KEY="$AGE_PRIVATE_KEY" sops decrypt "$OPENCODE_SECRET_FILE" > "${BASE_DIR}/.config/opencode/opencode.env"
        chmod 600 "${BASE_DIR}/.config/opencode/opencode.env"
    fi
    rm -f "$OPENCODE_SECRET_FILE"
    echo "   • Decrypted credentials to ${BASE_DIR}/.config/opencode/opencode.env"
fi

# Source OpenCode credentials into ambient environment
if [ -f "${BASE_DIR}/.config/opencode/opencode.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "${BASE_DIR}/.config/opencode/opencode.env"
    set +a
    if [ -n "${OPENCODE_GO_API_KEY:-}" ]; then
        export OPENCODE_API_KEY="$OPENCODE_GO_API_KEY"
    fi
fi

# 3. Decrypt repository credentials (organization token or fetch secret)
if [ -f "${BASE_DIR}/secrets/org/token" ]; then
    if [ -z "${GH_REPO:-}" ]; then
        echo "ERROR: GH_REPO environment variable is required when using organization credentials." >&2
        exit 1
    fi
    echo "🔐 Decrypting organization token from ${BASE_DIR}/secrets/org/token..."
    GH_TOKEN=$(SOPS_AGE_KEY="$AGE_PRIVATE_KEY" sops decrypt "${BASE_DIR}/secrets/org/token" 2>/dev/null | tr -d '\r\n')
    if [ -z "$GH_TOKEN" ]; then
        echo "ERROR: Failed to decrypt organization token using AGE_PRIVATE_KEY." >&2
        rm -rf "${BASE_DIR}/secrets/org"
        exit 1
    fi
    rm -f "${BASE_DIR}/secrets/org/token"
    echo "🧹 Purged encrypted organization token from disk."
    export ORG_TOKEN="1"
    export TRACKER="${TRACKER:-github}"
else
    FETCH_SECRET_FILE=""
    if [ -f "${BASE_DIR}/secrets/repo/fetch.env" ]; then
        FETCH_SECRET_FILE="${BASE_DIR}/secrets/repo/fetch.env"
    elif [ -f "${BASE_DIR}/secrets/fetch.env" ]; then
        FETCH_SECRET_FILE="${BASE_DIR}/secrets/fetch.env"
    fi

    if [ -z "$FETCH_SECRET_FILE" ]; then
        echo "ERROR: Repository secret not found (expected /root/secrets/org/token or /root/secrets/repo/fetch.env)." >&2
        exit 1
    fi

    echo "🔐 Decrypting repository fetch secret from $FETCH_SECRET_FILE..."
    DECRYPTED_FETCH=$(SOPS_AGE_KEY="$AGE_PRIVATE_KEY" sops decrypt "$FETCH_SECRET_FILE" 2>/dev/null || true)
    if [ -z "$DECRYPTED_FETCH" ]; then
        echo "ERROR: Failed to decrypt repository fetch secret using AGE_PRIVATE_KEY." >&2
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
    unset DECRYPTED_FETCH
fi

if [ -z "${GH_REPO:-}" ]; then
    echo "ERROR: GH_REPO is not set." >&2
    exit 1
fi

if [ -z "${GH_TOKEN:-}" ]; then
    echo "ERROR: GH_TOKEN is not set." >&2
    exit 1
fi

# 4. Clone repository
REPO_NAME=$(basename "$GH_REPO")
TARGET_DIR="${BASE_DIR}/$REPO_NAME"

git config --global advice.detachedHead false
git config --global user.name "Software Factory"
git config --global user.email "factory@modal.internal"

if [ ! -d "$TARGET_DIR" ]; then
    echo "🏝️  Cloning $GH_REPO..."
    GIT_ASKPASS=echo git clone \
        "https://oauth2:${GH_TOKEN}@github.com/${GH_REPO}.git" "$TARGET_DIR"
fi

cd "$TARGET_DIR"

# 5. Check out target branch
if [ -n "${TARGET_BRANCH:-}" ]; then
    BRANCH_NAME="$TARGET_BRANCH"
else
    BRANCH_NAME="factory/${FEATURE_SLUG}"
fi
echo "🌿 Checking out branch $BRANCH_NAME..."
if [ "$BRANCH_NAME" = "main" ] || [ "$BRANCH_NAME" = "master" ]; then
    if git show-ref --verify --quiet "refs/remotes/origin/$BRANCH_NAME"; then
        git checkout -B "$BRANCH_NAME" "origin/$BRANCH_NAME" --quiet
    else
        git checkout "$BRANCH_NAME" --quiet || true
    fi
else
    REMOTE_EXISTS=false
    if git ls-remote --heads origin "refs/heads/$BRANCH_NAME" 2>/dev/null | grep -q "refs/heads/$BRANCH_NAME"; then
        REMOTE_EXISTS=true
    fi

    if [ "$REMOTE_EXISTS" = true ]; then
        echo "   • Tracking existing remote branch origin/$BRANCH_NAME"
        git fetch origin "+refs/heads/${BRANCH_NAME}:refs/remotes/origin/${BRANCH_NAME}" --quiet || true
        git checkout -B "$BRANCH_NAME" "origin/${BRANCH_NAME}" --quiet
    elif [ "$PREVIEW_ONLY" = true ]; then
        echo "   • Remote branch $BRANCH_NAME does not exist; checking out main for preview"
        if git show-ref --verify --quiet "refs/remotes/origin/main"; then
            git checkout -B "main" "origin/main" --quiet
        elif git show-ref --verify --quiet "refs/heads/main"; then
            git checkout "main" --quiet
        else
            git checkout -B "main" --quiet
        fi
    else
        echo "   • Forking new feature branch $BRANCH_NAME from main"
        if git show-ref --verify --quiet "refs/remotes/origin/main"; then
            git checkout -B "$BRANCH_NAME" "origin/main" --quiet
        elif git show-ref --verify --quiet "refs/heads/main"; then
            git checkout -B "$BRANCH_NAME" "main" --quiet
        else
            git checkout -B "$BRANCH_NAME" --quiet
        fi
    fi
fi

# 6. Decrypt repository environment secrets if env.map is present
ENV_MAP_FILE="${BASE_DIR}/secrets/repo/env.map"
if [ -f "$ENV_MAP_FILE" ]; then
    echo "📄 Decrypting repository environment secrets into $TARGET_DIR..."
    while IFS= read -r line || [ -n "$line" ]; do
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "${line// }" ]] && continue
        if [[ "$line" =~ ^([^=]+)=(.*)$ ]]; then
            src_rel="${BASH_REMATCH[1]}"
            dest_rel="${BASH_REMATCH[2]}"
            src_rel=$(echo "$src_rel" | tr -d '\r' | xargs)
            dest_rel=$(echo "$dest_rel" | tr -d '\r' | xargs)
            dest_rel="${dest_rel#/}"

            src_file="${BASE_DIR}/secrets/repo/$src_rel"
            dest_file="$TARGET_DIR/$dest_rel"

            if [ ! -f "$src_file" ]; then
                echo "ERROR: Mapped repository secret file not found at $src_file." >&2
                rm -rf "${BASE_DIR}/secrets/repo"
                exit 1
            fi

            mkdir -p "$(dirname "$dest_file")"
            if ! SOPS_AGE_KEY="$AGE_PRIVATE_KEY" sops decrypt "$src_file" > "$dest_file"; then
                echo "ERROR: Failed to decrypt $src_file using AGE_PRIVATE_KEY." >&2
                rm -f "$dest_file"
                rm -rf "${BASE_DIR}/secrets/repo"
                exit 1
            fi
            chmod 600 "$dest_file"
            echo "   • Decrypted $src_rel -> $dest_rel"
        fi
    done < "$ENV_MAP_FILE"
fi

# 7. Scrub repository secrets staging directory and temporary SOPS credentials
if [ -d "${BASE_DIR}/secrets/repo" ]; then
    rm -rf "${BASE_DIR}/secrets/repo"
    echo "🧹 Purged repository secrets staging directory."
fi
if [ -d "${BASE_DIR}/secrets/org" ]; then
    rm -rf "${BASE_DIR}/secrets/org"
    echo "🧹 Purged organization secrets staging directory."
fi

rm -rf ~/.config/sops
unset SOPS_AGE_KEY
unset SOPS_AGE_KEY_FILE
unset AGE_PRIVATE_KEY
echo "🧹 Purged temporary SOPS credentials (~/.config/sops)."

# CRITICAL: Preserve GH_TOKEN for git branch pushing per ADR 0028 & Issue 05
export GH_TOKEN="$GH_TOKEN"
export GITHUB_TOKEN="$GH_TOKEN"

# 8. Ensure dependencies are installed in factory harness and target repository
FACTORY_DIR="${BASE_DIR}/factory"
if [ ! -d "${FACTORY_DIR}/node_modules" ]; then
    echo "📦 Installing factory harness dependencies..."
    (cd "$FACTORY_DIR" && pnpm install --shamefully-hoist)
fi

if [ -f "$TARGET_DIR/package.json" ] && [ ! -d "$TARGET_DIR/node_modules" ]; then
    if [ "${DEV_PREVIEW:-0}" = "1" ]; then
        echo "PREVIEW_STAGE:INSTALLING_DEPS"
    fi
    if [ -f "$TARGET_DIR/package-lock.json" ] && [ ! -f "$TARGET_DIR/pnpm-lock.yaml" ]; then
        echo "📦 Installing target repository dependencies (npm)..."
        (cd "$TARGET_DIR" && npm install)
    else
        echo "📦 Installing target repository dependencies (pnpm)..."
        (cd "$TARGET_DIR" && pnpm install)
    fi
fi

# 9. Execute in-sandbox pipeline
if [ "${PREVIEW_ONLY:-0}" = "1" ]; then
    echo "⏩ Preview-only mode: bypassing Assembly Line Pipeline agents."
    EXIT_CODE=0
else
    echo "🚀 Launching in-sandbox Assembly Line Pipeline..."
    CMD_ARGS=(
        "--workspace" "$TARGET_DIR"
        "--feature" "$FEATURE_SLUG"
    )
    if [ -n "$ISSUE_ID" ]; then
        CMD_ARGS+=("--issue" "$ISSUE_ID")
    fi
    if [ -n "$MODEL_ID" ]; then
        CMD_ARGS+=("--model" "$MODEL_ID")
    fi
    if [ -n "${TRACKER:-}" ]; then
        CMD_ARGS+=("--tracker" "$TRACKER")
    fi

    set +e
    export PYTHONUNBUFFERED=1
    node --experimental-strip-types "${FACTORY_DIR}/pipeline.ts" "${CMD_ARGS[@]}"
    EXIT_CODE=$?
    set -e

    echo ""
    echo "🏁 Pipeline completed with exit code: $EXIT_CODE"

    if [ "$EXIT_CODE" -ne 0 ]; then
        echo "❌ Pipeline failed; dev server will not be started."
        exit "$EXIT_CODE"
    fi
fi

# 10. Dev preview keep-alive daemon
if [ "${DEV_PREVIEW:-0}" = "1" ]; then
    echo ""
    echo "================================================================"
    echo "🌟 Launching Dev Preview Keep-Alive Daemon"
    echo "PREVIEW_STAGE:STARTING_DEV"
    echo "  • Working Directory: ${TARGET_DIR}"
    echo "  • Dev Command: pnpm dev --port 3000 --host 0.0.0.0"
    echo "  • Preview URL: https://3000.mahesh0.dev"
    echo "================================================================"

    cd "$TARGET_DIR"

    DEV_PID=""
    cleanup_dev() {
        echo ""
        echo "🛑 Shutting down dev server keep-alive daemon..."
        if [ -n "${WATCHER_PID:-}" ] && kill -0 "$WATCHER_PID" 2>/dev/null; then
            kill -TERM "$WATCHER_PID" 2>/dev/null || true
        fi
        if [ -n "$DEV_PID" ]; then
            kill -TERM -- -"$DEV_PID" 2>/dev/null || kill -TERM "$DEV_PID" 2>/dev/null || true
            wait "$DEV_PID" 2>/dev/null || true
        fi
        exit 0
    }
    trap cleanup_dev SIGTERM SIGINT SIGHUP

    pnpm dev --port 3000 --host 0.0.0.0 &
    DEV_PID=$!

    echo "📡 Dev server running with PID ${DEV_PID}."
    echo "⏳ Container entering active serving keep-alive state (https://3000.mahesh0.dev)..."

    # Maintain serving keep-alive state until process termination or cancellation
    wait "$DEV_PID"
    DEV_EXIT_CODE=$?
    echo "🛑 Dev server process exited with code ${DEV_EXIT_CODE}."
    exit "$DEV_EXIT_CODE"
fi

exit "$EXIT_CODE"
