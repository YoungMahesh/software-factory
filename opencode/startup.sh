#!/usr/bin/env bash
set -euo pipefail

REF="${1:-main}"
OPENCODE_PORT="${OPENCODE_PORT:-4096}"

# 1. Configure OpenCode Go auth if key is present
if [ -n "${OPENCODE_GO_API_KEY:-}" ]; then
    mkdir -p ~/.local/share/opencode
    cat <<EOF > ~/.local/share/opencode/auth.json
{
  "opencode-go": {
    "type": "api",
    "key": "$OPENCODE_GO_API_KEY"
  }
}
EOF
fi

# 2. Clone repository
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
    echo "🏖️  Cloning $GH_REPO (ref: $REF)..."
    GIT_ASKPASS=echo git clone --quiet --depth 1 --branch "$REF" --no-single-branch \
        "https://oauth2:${GH_TOKEN}@github.com/${GH_REPO}.git" "$TARGET_DIR"
fi

cd "$TARGET_DIR"

# 3. Decrypt / write environment keys if provided
if [ -n "${DOTENV_PRIVATE_KEY:-}" ]; then
    echo "DOTENV_PRIVATE_KEY=$DOTENV_PRIVATE_KEY" > .env.keys
fi

# 4. Install dependencies if package manifest exists
if [ -f "pnpm-lock.yaml" ]; then
    pnpm install
elif [ -f "package.json" ]; then
    npm install
fi

# 5. Launch OpenCode server
echo "🏖️  Starting OpenCode server on port $OPENCODE_PORT..."
exec opencode serve --hostname=0.0.0.0 --port="$OPENCODE_PORT" --log-level=DEBUG --print-logs
