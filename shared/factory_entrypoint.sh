#!/usr/bin/env bash
set -euo pipefail

FEATURE_SLUG=""
ISSUE_ID=""
MODEL_ID=""
TRACKER="${TRACKER:-}"

DEV_PREVIEW="${DEV_PREVIEW:-0}"
SNAPSHOT_RESUME="${SNAPSHOT_RESUME:-0}"

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
        --snapshot-resume)
            SNAPSHOT_RESUME="1"
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--feature <slug>] [--issue <id>] [--model <model>] [--tracker <github|local>] [--branch <branch>] [--dev] [--preview-only] [--snapshot-resume]"
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
    echo "  • Dev Preview: Enabled (port 3000 -> Modal Application Tunnel)"
fi
if [ "${SNAPSHOT_RESUME:-0}" = "1" ]; then
    echo "  • Snapshot Resumption: Enabled (Fast-path warm cold start)"
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
    if [ "${SNAPSHOT_RESUME:-0}" = "1" ] && [ -f "${BASE_DIR}/.factory.env" ]; then
        echo "⚡ Resuming from snapshot; AGE_PRIVATE_KEY check bypassed (.factory.env present)."
    else
        echo "ERROR: AGE_PRIVATE_KEY is not set in the environment. Ensure the Modal secret 'share0' is mounted." >&2
        exit 1
    fi
else
    mkdir -p ~/.config/sops/age
    echo "$AGE_PRIVATE_KEY" > ~/.config/sops/age/keys.txt
    chmod 600 ~/.config/sops/age/keys.txt
    export SOPS_AGE_KEY="$AGE_PRIVATE_KEY"
    export SOPS_AGE_KEY_FILE="${HOME:-/root}/.config/sops/age/keys.txt"
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
        if [ "${SNAPSHOT_RESUME:-0}" = "1" ] && [ -f "${BASE_DIR}/.factory.env" ]; then
            echo "🔐 Sourcing credentials from existing ${BASE_DIR}/.factory.env for snapshot resumption..."
            set -a
            # shellcheck disable=SC1090
            source "${BASE_DIR}/.factory.env"
            set +a
        else
            echo "ERROR: Repository secret not found (expected /root/secrets/org/token or /root/secrets/repo/fetch.env)." >&2
            exit 1
        fi
    else

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
export GIT_TERMINAL_PROMPT=0

# Resolve target branch
if [ -n "${TARGET_BRANCH:-}" ]; then
    BRANCH_NAME="$TARGET_BRANCH"
else
    BRANCH_NAME="factory/${FEATURE_SLUG}"
fi

# Dev preview supervisor function
start_dev_preview_supervisor() {
    export __VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS="${__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS:-.modal.host}"

    echo ""
    echo "================================================================"
    echo "🌟 Launching Dev Preview Keep-Alive Daemon"
    echo "PREVIEW_STAGE:STARTING_DEV"
    echo "  • Working Directory: ${TARGET_DIR}"
    echo "  • Dev Command: pnpm dev --port 3000 --host 0.0.0.0"
    echo "  • Preview: Modal Application Tunnel (port 3000)"
    echo "  • Allowed Hosts: ${__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS}"
    echo "================================================================"

    cd "$TARGET_DIR"

    DEV_PID=""
    SUPERVISOR_STOPPED=0
    cleanup_dev() {
        echo ""
        echo "🛑 Shutting down dev server supervisor daemon..."
        SUPERVISOR_STOPPED=1
        if [ -n "$DEV_PID" ]; then
            kill -TERM -- -"$DEV_PID" 2>/dev/null || kill -TERM "$DEV_PID" 2>/dev/null || true
            wait "$DEV_PID" 2>/dev/null || true
        fi
        exit 0
    }
    trap cleanup_dev SIGTERM SIGINT SIGHUP

    while [ "$SUPERVISOR_STOPPED" -eq 0 ]; do
        pnpm dev --port 3000 --host 0.0.0.0 &
        DEV_PID=$!

        echo "📡 Dev server running with PID ${DEV_PID}."
        echo "⏳ Container entering active serving keep-alive state..."

        # Maintain serving keep-alive state until process termination or cancellation
        set +e
        wait "$DEV_PID"
        DEV_EXIT_CODE=$?
        set -e

        if [ "$SUPERVISOR_STOPPED" -eq 1 ]; then
            break
        fi

        if [ "${DEV_PREVIEW_ONCE:-0}" = "1" ]; then
            exit "$DEV_EXIT_CODE"
        fi

        echo "⚠️ Dev server process exited with code ${DEV_EXIT_CODE}. Auto-restarting in 1s..."
        sleep 1
    done
    exit 0
}

# 5. Fast-path snapshot resumption (instant cold start)
FAST_PATH_RESUMED=0
if [ "${SNAPSHOT_RESUME:-0}" = "1" ]; then
    echo "⚡ Snapshot fast-path resumption requested (SNAPSHOT_RESUME=1)..."
    if [ -d "$TARGET_DIR/.git" ]; then
        SNAPSHOT_COMMIT=$(git -C "$TARGET_DIR" rev-parse HEAD 2>/dev/null || echo "")
        echo "   • Resuming from snapshot commit: ${SNAPSHOT_COMMIT:-unknown}"

        ORIGIN_URL=$(git -C "$TARGET_DIR" remote get-url origin 2>/dev/null || echo "")
        if [ -n "${GH_TOKEN:-}" ] && [[ ! "$ORIGIN_URL" =~ ^(/|file://) ]]; then
            git -C "$TARGET_DIR" remote set-url origin "https://oauth2:${GH_TOKEN}@github.com/${GH_REPO}.git" 2>/dev/null || true
        fi

        echo "🌿 Fast-fetching target branch ${BRANCH_NAME}..."
        git -C "$TARGET_DIR" fetch origin "+refs/heads/${BRANCH_NAME}:refs/remotes/origin/${BRANCH_NAME}" --quiet 2>/dev/null || \
        git -C "$TARGET_DIR" fetch origin --quiet 2>/dev/null || true

        CHECKOUT_OK=0
        if git -C "$TARGET_DIR" show-ref --verify --quiet "refs/remotes/origin/${BRANCH_NAME}"; then
            git -C "$TARGET_DIR" checkout -B "${BRANCH_NAME}" "origin/${BRANCH_NAME}" --quiet && CHECKOUT_OK=1
        elif git -C "$TARGET_DIR" show-ref --verify --quiet "refs/heads/${BRANCH_NAME}"; then
            git -C "$TARGET_DIR" checkout "${BRANCH_NAME}" --quiet && CHECKOUT_OK=1
        elif git -C "$TARGET_DIR" show-ref --verify --quiet "refs/remotes/origin/main"; then
            if [ "${PREVIEW_ONLY:-0}" = "1" ]; then
                git -C "$TARGET_DIR" checkout -B "main" "origin/main" --quiet && CHECKOUT_OK=1
            else
                git -C "$TARGET_DIR" checkout -B "${BRANCH_NAME}" "origin/main" --quiet && CHECKOUT_OK=1
            fi
        elif git -C "$TARGET_DIR" show-ref --verify --quiet "refs/heads/main"; then
            if [ "${PREVIEW_ONLY:-0}" = "1" ]; then
                git -C "$TARGET_DIR" checkout "main" --quiet && CHECKOUT_OK=1
            else
                git -C "$TARGET_DIR" checkout -B "${BRANCH_NAME}" "main" --quiet && CHECKOUT_OK=1
            fi
        fi

        if [ "$CHECKOUT_OK" -eq 1 ]; then
            TARGET_COMMIT=$(git -C "$TARGET_DIR" rev-parse HEAD 2>/dev/null || echo "")
            echo "   • Checked out ref ${BRANCH_NAME} at commit: ${TARGET_COMMIT}"

            # Dependency drift detection
            DRIFT=0
            if [ -n "$SNAPSHOT_COMMIT" ] && [ -n "$TARGET_COMMIT" ] && [ "$SNAPSHOT_COMMIT" != "$TARGET_COMMIT" ]; then
                DIFF_MANIFESTS=$(git -C "$TARGET_DIR" diff --name-only "$SNAPSHOT_COMMIT" "$TARGET_COMMIT" -- package.json pnpm-lock.yaml package-lock.json 2>/dev/null || echo "")
                if [ -n "$DIFF_MANIFESTS" ]; then
                    DRIFT=1
                    echo "PREVIEW_STAGE:INSTALLING_DEPS"
                    echo "📦 Dependency manifest drift detected (${DIFF_MANIFESTS}). Running incremental dependency installation..."
                    if [ -f "$TARGET_DIR/package-lock.json" ] && [ ! -f "$TARGET_DIR/pnpm-lock.yaml" ]; then
                        (cd "$TARGET_DIR" && npm install --prefer-offline 2>/dev/null || (cd "$TARGET_DIR" && npm install))
                    else
                        (cd "$TARGET_DIR" && pnpm install --prefer-offline)
                    fi
                fi
            fi

            if [ "$DRIFT" -eq 0 ]; then
                echo "⚡ No dependency manifest drift detected; skipping package installation."
            fi

            FAST_PATH_RESUMED=1
            echo "⚡ Fast-path snapshot resumption successful (<3s cold start)."

            # Launch dev preview directly if in preview mode
            if [ "${DEV_PREVIEW:-0}" = "1" ]; then
                start_dev_preview_supervisor
            fi
        else
            echo "⚠️ Failed to fetch or checkout ${BRANCH_NAME} during fast-path resumption; falling back to clean init..." >&2
        fi
    else
        echo "⚠️ Target Project Workspace ${TARGET_DIR} is not a valid git repository; falling back to clean init..." >&2
    fi
fi

if [ ! -d "$TARGET_DIR" ]; then
    echo "🏝️  Cloning $GH_REPO..."
    GIT_ASKPASS=echo git clone \
        "https://oauth2:${GH_TOKEN}@github.com/${GH_REPO}.git" "$TARGET_DIR"
fi

cd "$TARGET_DIR"

# 6. Check out target branch
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

# Persist credentials to protected container environment file per ADR 0038
FACTORY_ENV_FILE="${BASE_DIR}/.factory.env"
echo "🔐 Persisting container environment to ${FACTORY_ENV_FILE}..."
touch "$FACTORY_ENV_FILE"
chmod 600 "$FACTORY_ENV_FILE"

cat << EOF > "$FACTORY_ENV_FILE"
export GH_TOKEN="${GH_TOKEN:-}"
export GITHUB_TOKEN="${GH_TOKEN:-}"
export GH_REPO="${GH_REPO:-}"
EOF

if [ -n "${OPENCODE_API_KEY:-}" ]; then
    echo "export OPENCODE_API_KEY=\"${OPENCODE_API_KEY}\"" >> "$FACTORY_ENV_FILE"
fi
if [ -n "${OPENCODE_GO_API_KEY:-}" ]; then
    echo "export OPENCODE_GO_API_KEY=\"${OPENCODE_GO_API_KEY}\"" >> "$FACTORY_ENV_FILE"
fi
if [ -n "${EXA_API_KEY:-}" ]; then
    echo "export EXA_API_KEY=\"${EXA_API_KEY}\"" >> "$FACTORY_ENV_FILE"
fi
if [ -n "${CONTEXT7_API_KEY:-}" ]; then
    echo "export CONTEXT7_API_KEY=\"${CONTEXT7_API_KEY}\"" >> "$FACTORY_ENV_FILE"
fi
if [ -n "${TRACKER:-}" ]; then
    echo "export TRACKER=\"${TRACKER}\"" >> "$FACTORY_ENV_FILE"
fi
if [ -n "${ORG_TOKEN:-}" ]; then
    echo "export ORG_TOKEN=\"${ORG_TOKEN}\"" >> "$FACTORY_ENV_FILE"
fi

chmod 600 "$FACTORY_ENV_FILE"

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
    start_dev_preview_supervisor
fi

exit "$EXIT_CODE"
