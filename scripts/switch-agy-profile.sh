#!/usr/bin/env bash
set -euo pipefail

# ./scripts/switch-agy-profile.sh anv
# ./scripts/switch-agy-profile.sh m47
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECRETS_DIR="${SECRETS_DIR:-$SCRIPT_DIR/../secrets}"
TARGET_DIR="${TARGET_DIR:-$HOME/.gemini/antigravity-cli}"
TARGET_FILE="$TARGET_DIR/antigravity-oauth-token"

usage() {
    echo "Usage: $0 {anv|m47}" >&2
    exit 1
}

if [ "$#" -ne 1 ]; then
    usage
fi

case "$1" in
    anv)
        SOURCE_FILE="$SECRETS_DIR/antigravity-oauth-token-anv.json"
        PROFILE="anv"
        ;;
    m47)
        SOURCE_FILE="$SECRETS_DIR/antigravity-oauth-token.json"
        PROFILE="m47"
        ;;
    -h|--help)
        echo "Usage: $0 {anv|m47}"
        echo
        echo "Switch Antigravity CLI OAuth profile:"
        echo "  anv  - Decrypt secrets/antigravity-oauth-token-anv.json to ~/.gemini/antigravity-cli/antigravity-oauth-token"
        echo "  m47  - Decrypt secrets/antigravity-oauth-token.json to ~/.gemini/antigravity-cli/antigravity-oauth-token"
        exit 0
        ;;
    *)
        echo "ERROR: Unknown profile: $1" >&2
        usage
        ;;
esac

if [ ! -f "$SOURCE_FILE" ]; then
    echo "ERROR: Secret file not found: $SOURCE_FILE" >&2
    exit 1
fi

mkdir -p "$TARGET_DIR"

TMP_FILE="$(mktemp "${TARGET_DIR}/antigravity-oauth-token.XXXXXX")"
trap 'rm -f "$TMP_FILE"' EXIT
chmod 600 "$TMP_FILE"

sops decrypt "$SOURCE_FILE" > "$TMP_FILE"
mv -f "$TMP_FILE" "$TARGET_FILE"
trap - EXIT

chmod 600 "$TARGET_FILE"

echo "Switched Antigravity CLI profile to: $PROFILE"
