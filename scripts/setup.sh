#!/usr/bin/env bash
set -euo pipefail

DECRYPT_MODAL=false

while [ "$#" -gt 0 ]; do
    case "$1" in
        --modal)
            DECRYPT_MODAL=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--modal]"
            exit 0
            ;;
        *)
            echo "ERROR: Unknown option: $1" >&2
            echo "Usage: $0 [--modal]" >&2
            exit 1
            ;;
    esac
done

if [ "$DECRYPT_MODAL" = true ]; then
    sops decrypt secrets/modal.toml > ~/.modal.toml
    chmod 600 ~/.modal.toml
fi

mkdir -p ~/.gemini/antigravity-cli
sops decrypt secrets/antigravity-oauth-token.json > ~/.gemini/antigravity-cli/antigravity-oauth-token
chmod 600 ~/.gemini/antigravity-cli/antigravity-oauth-token
