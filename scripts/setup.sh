#!/usr/bin/env bash
set -euo pipefail

DECRYPT_MODAL=false
DECRYPT_AGY=false
DECRYPT_OPENCODE=false
DECRYPT_PI=false

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
        --pi)
            DECRYPT_PI=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--modal] [--agy] [--opencode] [--pi]"
            exit 0
            ;;
        *)
            echo "ERROR: Unknown option: $1" >&2
            echo "Usage: $0 [--modal] [--agy] [--opencode] [--pi]" >&2
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

    # Pre-populate Antigravity ACP credentials for T3 Code and fallback profile
    if command -v python3 >/dev/null 2>&1; then
        python3 -c '
import hashlib, json, os

token_path = os.path.expanduser("~/.gemini/antigravity-cli/antigravity-oauth-token")
if os.path.exists(token_path):
    try:
        with open(token_path, "r") as f:
            data = json.load(f)
        refresh_token = data.get("token", {}).get("refresh_token") or data.get("refresh_token")
        if refresh_token:
            acp_token = {
                "client_id": "dummy-client-id.apps.googleusercontent.com",
                "client_secret": "dummy-client-secret",
                "refresh_token": refresh_token,
                "token_uri": "https://oauth2.googleapis.com/token",
                "scopes": [
                    "https://www.googleapis.com/auth/cloud-platform",
                    "https://www.googleapis.com/auth/userinfo.email",
                    "https://www.googleapis.com/auth/aicode"
                ]
            }
            acp_settings = {"auth": {"type": "oauth-personal"}}
            t3_hash = hashlib.sha256(b"antigravity").hexdigest()
            target_dirs = [
                f"/root/.t3/userdata/providers/antigravity/{t3_hash}/antigravity-acp",
                os.path.expanduser("~/.gemini/antigravity-acp")
            ]
            for d in target_dirs:
                os.makedirs(d, mode=0o700, exist_ok=True)
                tok_file = os.path.join(d, "acp_token.json")
                set_file = os.path.join(d, "settings.json")
                with open(tok_file, "w") as fp:
                    json.dump(acp_token, fp, indent=2)
                os.chmod(tok_file, 0o600)
                with open(set_file, "w") as fp:
                    json.dump(acp_settings, fp, indent=2)
                os.chmod(set_file, 0o600)

            t3_settings_path = "/root/.t3/userdata/settings.json"
            os.makedirs(os.path.dirname(t3_settings_path), mode=0o755, exist_ok=True)
            settings = {}
            if os.path.exists(t3_settings_path):
                try:
                    with open(t3_settings_path, "r") as fp:
                        settings = json.load(fp)
                except Exception:
                    settings = {}
            if "providerInstances" not in settings:
                settings["providerInstances"] = {}
            if "antigravity" not in settings["providerInstances"]:
                settings["providerInstances"]["antigravity"] = {
                    "driver": "antigravity",
                    "displayName": "Antigravity",
                    "enabled": True
                }
            else:
                settings["providerInstances"]["antigravity"]["enabled"] = True
            with open(t3_settings_path, "w") as fp:
                json.dump(settings, fp, indent=2)
            os.chmod(t3_settings_path, 0o644)
    except Exception as e:
        print(f"Warning: Failed to setup Antigravity ACP credentials: {e}")
' 2>/dev/null || true
    fi
fi

if [ "$DECRYPT_OPENCODE" = true ] || [ "$DECRYPT_PI" = true ]; then
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

if [ "$DECRYPT_PI" = true ]; then
    mkdir -p ~/.pi/agent
fi
