#!/usr/bin/env bash
set -euo pipefail

# ./scripts/switch-agy-profile.sh anv
# ./scripts/switch-agy-profile.sh m47
# ./scripts/switch-agy-profile.sh mgh
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECRETS_DIR="${SECRETS_DIR:-$SCRIPT_DIR/../secrets}"
TARGET_DIR="${TARGET_DIR:-$HOME/.gemini/antigravity-cli}"
TARGET_FILE="$TARGET_DIR/antigravity-oauth-token"
PROFILES_DIR="${PROFILES_DIR:-$TARGET_DIR/profiles}"

usage() {
    echo "Usage: $0 {anv|m47|mgh}" >&2
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
    mgh)
        SOURCE_FILE="$SECRETS_DIR/antigravity-oauth-token-mgh.json"
        PROFILE="mgh"
        ;;
    -h|--help)
        echo "Usage: $0 {anv|m47|mgh}"
        echo
        echo "Switch Antigravity CLI OAuth profile:"
        echo "  anv  - Switch to ANV profile (secrets/antigravity-oauth-token-anv.json or ~/.gemini/antigravity-cli/profiles/anv)"
        echo "  m47  - Switch to M47 profile (secrets/antigravity-oauth-token.json or ~/.gemini/antigravity-cli/profiles/m47)"
        echo "  mgh  - Switch to MGH profile (secrets/antigravity-oauth-token-mgh.json or ~/.gemini/antigravity-cli/profiles/mgh)"
        exit 0
        ;;
    *)
        echo "ERROR: Unknown profile: $1" >&2
        usage
        ;;
esac

mkdir -p "$TARGET_DIR"

if [ -f "$PROFILES_DIR/$PROFILE" ]; then
    cp -f "$PROFILES_DIR/$PROFILE" "$TARGET_FILE"
    chmod 600 "$TARGET_FILE"
    echo "Switched Antigravity CLI profile to: $PROFILE"
    exit 0
fi

if [ ! -f "$SOURCE_FILE" ]; then
    echo "ERROR: Secret file not found: $SOURCE_FILE (and no profile found at $PROFILES_DIR/$PROFILE)" >&2
    exit 1
fi

TMP_FILE="$(mktemp "${TARGET_DIR}/antigravity-oauth-token.XXXXXX")"
trap 'rm -f "$TMP_FILE"' EXIT
chmod 600 "$TMP_FILE"

sops decrypt "$SOURCE_FILE" > "$TMP_FILE"
mv -f "$TMP_FILE" "$TARGET_FILE"
trap - EXIT

chmod 600 "$TARGET_FILE"

echo "Switched Antigravity CLI profile to: $PROFILE"
