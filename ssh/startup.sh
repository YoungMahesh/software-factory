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

if [ ! -d "$TARGET_DIR" ]; then
    echo "🏝️  Cloning $GH_REPO (ref: $REF)..."
    GIT_ASKPASS=echo git clone --quiet --depth 1 --branch "$REF" --no-single-branch \
        "https://oauth2:${GH_TOKEN}@github.com/${GH_REPO}.git" "$TARGET_DIR"
fi

cd "$TARGET_DIR"
grep -qxF "cd $TARGET_DIR" ~/.bashrc 2>/dev/null || echo "cd $TARGET_DIR" >> ~/.bashrc
grep -qxF "export HOSTNAME=0.0.0.0" ~/.bashrc 2>/dev/null || echo "export HOSTNAME=0.0.0.0" >> ~/.bashrc
grep -qxF "export PORT=${PORT:-3000}" ~/.bashrc 2>/dev/null || echo "export PORT=${PORT:-3000}" >> ~/.bashrc

# 2. Decrypt / write environment keys if provided
if [ -n "${DOTENV_PRIVATE_KEY:-}" ]; then
    echo "DOTENV_PRIVATE_KEY=$DOTENV_PRIVATE_KEY" > .env.keys
fi

# 3. Install dependencies if package manifest exists
if [ -f "pnpm-lock.yaml" ]; then
    pnpm install
elif [ -f "package.json" ]; then
    npm install
fi

# 4. Keep sandbox alive for interaction via modal shell / ssh
echo "🏝️  Sandbox Ready!"
exec sleep infinity
