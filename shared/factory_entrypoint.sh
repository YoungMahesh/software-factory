#!/usr/bin/env bash
set -euo pipefail

FEATURE_SLUG=""
ISSUE_ID=""
MODEL_ID=""

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
        -h|--help)
            echo "Usage: $0 --feature <slug> [--issue <id>] [--model <model>]"
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

if [ -z "$FEATURE_SLUG" ]; then
    echo "ERROR: Feature slug is required (--feature <slug> or positional argument)." >&2
    exit 1
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
echo "================================================================"

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

# 2. Ephemerally decrypt OpenCode credentials into ~/.config/opencode/opencode.env
OPENCODE_SECRET_FILE="/root/secrets/opencode.env"
if [ -f "$OPENCODE_SECRET_FILE" ]; then
    echo "🔑 Decrypting OpenCode credentials via Tooling Setup Script..."
    if [ -f "/root/scripts/setup.sh" ]; then
        bash /root/scripts/setup.sh --opencode
    else
        mkdir -p /root/.config/opencode
        SOPS_AGE_KEY="$AGE_PRIVATE_KEY" sops decrypt "$OPENCODE_SECRET_FILE" > /root/.config/opencode/opencode.env
        chmod 600 /root/.config/opencode/opencode.env
    fi
    rm -f "$OPENCODE_SECRET_FILE"
    echo "   • Decrypted credentials to /root/.config/opencode/opencode.env"
fi

# Source OpenCode credentials into ambient environment
if [ -f /root/.config/opencode/opencode.env ]; then
    set -a
    # shellcheck disable=SC1091
    source /root/.config/opencode/opencode.env
    set +a
    if [ -n "${OPENCODE_GO_API_KEY:-}" ]; then
        export OPENCODE_API_KEY="$OPENCODE_GO_API_KEY"
    fi
fi

# 3. Decrypt repository fetch secret
FETCH_SECRET_FILE=""
if [ -f "/root/secrets/repo/fetch.env" ]; then
    FETCH_SECRET_FILE="/root/secrets/repo/fetch.env"
elif [ -f "/root/secrets/fetch.env" ]; then
    FETCH_SECRET_FILE="/root/secrets/fetch.env"
fi

if [ -z "$FETCH_SECRET_FILE" ]; then
    echo "ERROR: Repository fetch secret not found at /root/secrets/repo/fetch.env." >&2
    exit 1
fi

echo "🔐 Decrypting repository fetch secret from $FETCH_SECRET_FILE..."
DECRYPTED_FETCH=$(SOPS_AGE_KEY="$AGE_PRIVATE_KEY" sops decrypt "$FETCH_SECRET_FILE" 2>/dev/null || true)
if [ -z "$DECRYPTED_FETCH" ]; then
    echo "ERROR: Failed to decrypt repository fetch secret using AGE_PRIVATE_KEY." >&2
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

if [ -z "${GH_REPO:-}" ]; then
    echo "ERROR: GH_REPO is not set in the decrypted fetch secret." >&2
    exit 1
fi

if [ -z "${GH_TOKEN:-}" ]; then
    echo "ERROR: GH_TOKEN is not set in the decrypted fetch secret." >&2
    exit 1
fi

# 4. Clone repository
REPO_NAME=$(basename "$GH_REPO")
TARGET_DIR="/root/$REPO_NAME"

git config --global advice.detachedHead false
git config --global user.name "Software Factory"
git config --global user.email "factory@modal.internal"

if [ ! -d "$TARGET_DIR" ]; then
    echo "🏝️  Cloning $GH_REPO..."
    GIT_ASKPASS=echo git clone --quiet \
        "https://oauth2:${GH_TOKEN}@github.com/${GH_REPO}.git" "$TARGET_DIR"
fi

cd "$TARGET_DIR"

# 5. Check out feature branch factory/<feature>
BRANCH_NAME="factory/${FEATURE_SLUG}"
echo "🌿 Checking out feature branch $BRANCH_NAME..."
REMOTE_EXISTS=false
if git ls-remote --heads origin "refs/heads/$BRANCH_NAME" 2>/dev/null | grep -q "refs/heads/$BRANCH_NAME"; then
    REMOTE_EXISTS=true
fi

if [ "$REMOTE_EXISTS" = true ]; then
    echo "   • Tracking existing remote branch origin/$BRANCH_NAME"
    git fetch origin "+refs/heads/${BRANCH_NAME}:refs/remotes/origin/${BRANCH_NAME}" --quiet || true
    git checkout -B "$BRANCH_NAME" "origin/${BRANCH_NAME}" --quiet
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

# 6. Decrypt repository environment secrets if env.map is present
ENV_MAP_FILE="/root/secrets/repo/env.map"
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

# 7. Scrub repository secrets staging directory and temporary SOPS credentials
if [ -d /root/secrets/repo ]; then
    rm -rf /root/secrets/repo
    echo "🧹 Purged repository secrets staging directory."
fi

rm -rf ~/.config/sops
unset AGE_PRIVATE_KEY
echo "🧹 Purged temporary SOPS credentials (~/.config/sops)."

# CRITICAL: Preserve GH_TOKEN for git branch pushing per ADR 0028 & Issue 05
export GH_TOKEN="$GH_TOKEN"
export GITHUB_TOKEN="$GH_TOKEN"

# 8. Ensure dependencies are installed in factory harness
if [ ! -d "/root/factory/node_modules" ]; then
    echo "📦 Installing factory harness dependencies..."
    (cd /root/factory && pnpm install --shamefully-hoist)
fi

# 9. Execute in-sandbox pipeline
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

set +e
node --experimental-strip-types /root/factory/pipeline.ts "${CMD_ARGS[@]}"
EXIT_CODE=$?
set -e

echo ""
echo "🏁 Pipeline completed with exit code: $EXIT_CODE"
exit "$EXIT_CODE"
