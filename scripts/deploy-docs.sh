#!/usr/bin/env bash
# ==============================================================================
# Build & Deploy Docs to Cloudflare Pages
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PROJECT_NAME="${CLOUDFLARE_PAGES_PROJECT:-modal-sandboxes-docs}"
BRANCH="${CLOUDFLARE_PAGES_BRANCH:-main}"

# 1. Load environment variables from .env if present
if [[ -f "${ROOT_DIR}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${ROOT_DIR}/.env"
    set +a
fi

# 2. Validate credentials
if [[ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]]; then
    echo "❌ Error: CLOUDFLARE_ACCOUNT_ID is not set in environment or .env" >&2
    exit 1
fi

if [[ -z "${CLOUDFLARE_API_TOKEN:-}" ]]; then
    echo "❌ Error: CLOUDFLARE_API_TOKEN is not set in environment or .env" >&2
    exit 1
fi

echo "==> Building documentation..."
cd "${ROOT_DIR}"

# Locate python/mkdocs binary (prefer repo venv if present)
if [[ -f "${ROOT_DIR}/.venv/bin/mkdocs" ]]; then
    MKDOCS="${ROOT_DIR}/.venv/bin/mkdocs"
elif [[ -f "/root/software-factory/.venv/bin/mkdocs" ]]; then
    MKDOCS="/root/software-factory/.venv/bin/mkdocs"
elif command -v mkdocs >/dev/null 2>&1; then
    MKDOCS="$(command -v mkdocs)"
else
    echo "❌ Error: mkdocs not found. Please install docs dependencies with: pip install '.[docs]'" >&2
    exit 1
fi

"${MKDOCS}" build --strict

if [[ ! -d "${ROOT_DIR}/site" ]]; then
    echo "❌ Error: Output directory 'site' was not generated." >&2
    exit 1
fi

echo "==> Deploying to Cloudflare Pages project: ${PROJECT_NAME}..."

# Locate wrangler CLI
if command -v wrangler >/dev/null 2>&1; then
    WRANGLER="wrangler"
else
    WRANGLER="npx wrangler"
fi

CI=1 ${WRANGLER} pages deploy "${ROOT_DIR}/site" \
    --project-name="${PROJECT_NAME}" \
    --branch="${BRANCH}" \
    --commit-dirty=true

echo ""
echo "✅ Documentation successfully built and deployed to Cloudflare Pages!"
echo "   Live URL: https://${PROJECT_NAME}.pages.dev"
