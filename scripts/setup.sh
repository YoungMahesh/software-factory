#!/usr/bin/env bash
set -euo pipefail

DECRYPT_MODAL=false
DECRYPT_AGY=false
DECRYPT_OPENCODE=false

while [ "$#" -gt 0 ]; do
    case "$1" in
        --modal)
            DECRYPT_MODAL=true
            shift
            ;;
        --agy)
            DECRYPT_AGY=true
            shift
            ;;
        --opencode)
            DECRYPT_OPENCODE=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--modal] [--agy] [--opencode]"
            exit 0
            ;;
        *)
            echo "ERROR: Unknown option: $1" >&2
            echo "Usage: $0 [--modal] [--agy] [--opencode]" >&2
            exit 1
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECRETS_DIR="${SECRETS_DIR:-$SCRIPT_DIR/../secrets}"

if [ "$DECRYPT_MODAL" = true ]; then
    sops decrypt "$SECRETS_DIR/modal.toml" > ~/.modal.toml
    chmod 600 ~/.modal.toml
fi

if [ "$DECRYPT_AGY" = true ]; then
    mkdir -p ~/.gemini/antigravity-cli
    sops decrypt "$SECRETS_DIR/antigravity-oauth-token.json" > ~/.gemini/antigravity-cli/antigravity-oauth-token
    chmod 600 ~/.gemini/antigravity-cli/antigravity-oauth-token
fi

if [ "$DECRYPT_OPENCODE" = true ]; then
    mkdir -p ~/.config/opencode
    sops decrypt "$SECRETS_DIR/opencode.env" > ~/.config/opencode/opencode.env
    chmod 600 ~/.config/opencode/opencode.env

    while IFS= read -r line || [ -n "$line" ]; do
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "${line// }" ]] && continue
        if [ -w /etc/environment ]; then
            grep -qxF "$line" /etc/environment 2>/dev/null || echo "$line" >> /etc/environment
        fi
        grep -qxF "export $line" ~/.bashrc 2>/dev/null || echo "export $line" >> ~/.bashrc
    done < ~/.config/opencode/opencode.env
fi
