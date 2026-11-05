#!/usr/bin/env bash
set -euo pipefail

DECRYPT_MODAL=false
DECRYPT_AGY=false
DECRYPT_T3=false
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
        --t3)
            DECRYPT_T3=true
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
            echo "Usage: $0 [--modal] [--agy] [--t3] [--opencode] [--pi]"
            exit 0
            ;;
        *)
            echo "ERROR: Unknown option: $1" >&2
            echo "Usage: $0 [--modal] [--agy] [--t3] [--opencode] [--pi]" >&2
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

if [ "$DECRYPT_AGY" = true ] || [ "$DECRYPT_T3" = true ]; then
    if [ -f "$SECRETS_DIR/antigravity.env" ]; then
        while IFS= read -r line || [ -n "$line" ]; do
            [[ "$line" =~ ^[[:space:]]*# ]] && continue
            [[ -z "${line// }" ]] && continue
            export "$line"
        done < <(sops decrypt "$SECRETS_DIR/antigravity.env" 2>/dev/null || true)
    fi
    mkdir -p ~/.gemini/antigravity-cli/profiles
    if [ -f "$SECRETS_DIR/antigravity-oauth-token.json" ]; then
        sops decrypt "$SECRETS_DIR/antigravity-oauth-token.json" > ~/.gemini/antigravity-cli/profiles/m47
        cp -f ~/.gemini/antigravity-cli/profiles/m47 ~/.gemini/antigravity-cli/antigravity-oauth-token
        chmod 600 ~/.gemini/antigravity-cli/profiles/m47 ~/.gemini/antigravity-cli/antigravity-oauth-token
    fi
    if [ -f "$SECRETS_DIR/antigravity-oauth-token-mgh.json" ]; then
        sops decrypt "$SECRETS_DIR/antigravity-oauth-token-mgh.json" > ~/.gemini/antigravity-cli/profiles/mgh
        chmod 600 ~/.gemini/antigravity-cli/profiles/mgh
    fi
    if [ -f "$SECRETS_DIR/antigravity-oauth-token-anv.json" ]; then
        sops decrypt "$SECRETS_DIR/antigravity-oauth-token-anv.json" > ~/.gemini/antigravity-cli/profiles/anv
        chmod 600 ~/.gemini/antigravity-cli/profiles/anv
    fi

    # Pre-populate Antigravity ACP credentials for T3 Code and fallback profile
    if command -v python3 >/dev/null 2>&1; then
        python3 -c '
import hashlib, json, os

accounts = [
    ("antigravity", "Antigravity", os.path.expanduser("~/.gemini/antigravity-cli/profiles/m47"), True),
    ("antigravity-mgh", "Antigravity (MGH)", os.path.expanduser("~/.gemini/antigravity-cli/profiles/mgh"), False),
    ("antigravity-anv", "Antigravity (ANV)", os.path.expanduser("~/.gemini/antigravity-cli/profiles/anv"), False),
]

t3_settings_path = os.path.expanduser("~/.t3/userdata/settings.json")
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

# Path to T3 caches directory (defaults to /root/.t3/caches in standard sandbox)
t3_cache_dir = os.path.expanduser("~/.t3/caches")
os.makedirs(t3_cache_dir, mode=0o755, exist_ok=True)

configured_antigravity = []
for instance_id, display_name, token_path, is_primary in accounts:
    if not os.path.exists(token_path) and is_primary:
        token_path = os.path.expanduser("~/.gemini/antigravity-cli/antigravity-oauth-token")

    if not os.path.exists(token_path):
        continue

    try:
        with open(token_path, "r") as f:
            data = json.load(f)
        refresh_token = data.get("token", {}).get("refresh_token") or data.get("refresh_token")
        if not refresh_token:
            continue

        acp_token = {
            "client_id": os.environ.get("ANTIGRAVITY_CLIENT_ID") or os.environ.get("GOOGLE_CLIENT_ID", "dummy-client-id.apps.googleusercontent.com"),
            "client_secret": os.environ.get("ANTIGRAVITY_CLIENT_SECRET") or os.environ.get("GOOGLE_CLIENT_SECRET", "dummy-client-secret"),
            "refresh_token": refresh_token,
            "token_uri": "https://oauth2.googleapis.com/token",
            "scopes": [
                "https://www.googleapis.com/auth/cloud-platform",
                "https://www.googleapis.com/auth/userinfo.email",
                "https://www.googleapis.com/auth/aicode"
            ]
        }
        acp_settings = {"auth": {"type": "oauth-personal"}}
        t3_hash = hashlib.sha256(instance_id.encode("utf-8")).hexdigest()
        target_dirs = [os.path.expanduser(f"~/.t3/userdata/providers/antigravity/{t3_hash}/antigravity-acp")]
        if is_primary:
            target_dirs.append(os.path.expanduser("~/.gemini/antigravity-acp"))

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

        settings["providerInstances"][instance_id] = {
            "driver": "antigravity",
            "displayName": display_name,
            "enabled": True
        }
        configured_antigravity.append(instance_id)

        t3_cache_file = os.path.join(t3_cache_dir, f"{instance_id}.json")
        cache_data = {
            "displayName": display_name,
            "showInteractionModeToggle": False,
            "enabled": True,
            "installed": True,
            "version": "1.3.0",
            "status": "ready",
            "auth": {
                "status": "authenticated",
                "type": "oauth-personal",
                "label": "Google account"
            },
            "setup": {
                "canAuthenticate": True,
                "canInstall": True
            },
            "checkedAt": "2026-10-27T12:00:00.000Z",
            "models": [
                {
                    "slug": "gemini-3.8-flash-high",
                    "name": "Gemini 3.8 Flash (High)",
                    "isCustom": False,
                    "isDefault": True,
                    "aliases": [f"{instance_id}-default"],
                    "capabilities": {"optionDescriptors": []}
                },
                {
                    "slug": "gemini-3.8-flash-medium",
                    "name": "Gemini 3.8 Flash (Medium)",
                    "isCustom": False,
                    "capabilities": {"optionDescriptors": []}
                },
                {
                    "slug": "gemini-3.8-flash-low",
                    "name": "Gemini 3.8 Flash (Low)",
                    "isCustom": False,
                    "capabilities": {"optionDescriptors": []}
                }
            ],
            "slashCommands": [],
            "skills": [],
            "supportsConversationRollback": False,
            "supportsTextGeneration": True,
            "instanceId": instance_id,
            "driver": "antigravity"
        }
        with open(t3_cache_file, "w") as fp:
            json.dump(cache_data, fp, indent=2)
        os.chmod(t3_cache_file, 0o644)
    except Exception as e:
        print(f"Warning: Failed to setup Antigravity ACP credentials for {instance_id}: {e}")

# Also check if OpenCode credentials are ready and configure OpenCode in T3
opencode_env_path = os.path.expanduser("~/.config/opencode/opencode.env")
has_opencode = bool(os.environ.get("OPENCODE_GO_API_KEY"))
if not has_opencode and os.path.exists(opencode_env_path):
    try:
        with open(opencode_env_path, "r") as ef:
            for eline in ef:
                if eline.startswith("OPENCODE_GO_API_KEY="):
                    val = eline.split("=", 1)[1].strip().strip("\"").strip(chr(39))
                    if val:
                        has_opencode = True
                        break
    except Exception:
        pass
if has_opencode:
    # Default binary path: /root/.opencode/bin/opencode
    opencode_bin = os.path.expanduser("~/.opencode/bin/opencode")
    if "opencode" not in settings["providerInstances"]:
        settings["providerInstances"]["opencode"] = {
            "driver": "opencode",
            "displayName": "OpenCode",
            "enabled": True,
            "binaryPath": opencode_bin
        }
    else:
        settings["providerInstances"]["opencode"]["enabled"] = True
        settings["providerInstances"]["opencode"]["binaryPath"] = opencode_bin

if "claudeAgent" not in settings["providerInstances"]:
    settings["providerInstances"]["claudeAgent"] = {
        "driver": "claudeAgent",
        "enabled": False
    }
if "codex" not in settings["providerInstances"]:
    settings["providerInstances"]["codex"] = {
        "driver": "codex",
        "enabled": False
    }

default_agy_instance = None
for candidate in ["antigravity-anv", "antigravity-mgh", "antigravity"]:
    if candidate in configured_antigravity:
        default_agy_instance = candidate
        break
if default_agy_instance is None and configured_antigravity:
    default_agy_instance = configured_antigravity[0]

if default_agy_instance:
    model_sel = {
        "instanceId": default_agy_instance,
        "model": "gemini-3.8-flash-low"
    }
    if not settings.get("sourceControlWriterModelSelection") or settings.get("sourceControlWriterModelSelection", {}).get("instanceId") == "codex":
        settings["sourceControlWriterModelSelection"] = model_sel
    if not settings.get("textGenerationModelSelection") or settings.get("textGenerationModelSelection", {}).get("instanceId") == "codex":
        settings["textGenerationModelSelection"] = model_sel

with open(t3_settings_path, "w") as fp:
    json.dump(settings, fp, indent=2)
os.chmod(t3_settings_path, 0o644)
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

    if [ "$DECRYPT_OPENCODE" = true ] && command -v python3 >/dev/null 2>&1; then
        python3 -c '
import json, os
t3_settings_path = os.path.expanduser("~/.t3/userdata/settings.json")
if os.path.exists(os.path.dirname(t3_settings_path)) or os.path.exists("/opt/t3"):
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
    # Default binary path: /root/.opencode/bin/opencode
    opencode_bin = os.path.expanduser("~/.opencode/bin/opencode")
    if "opencode" not in settings["providerInstances"]:
        settings["providerInstances"]["opencode"] = {
            "driver": "opencode",
            "displayName": "OpenCode",
            "enabled": True,
            "binaryPath": opencode_bin
        }
    else:
        settings["providerInstances"]["opencode"]["enabled"] = True
        settings["providerInstances"]["opencode"]["binaryPath"] = opencode_bin
    with open(t3_settings_path, "w") as fp:
        json.dump(settings, fp, indent=2)
    os.chmod(t3_settings_path, 0o644)
' 2>/dev/null || true
    fi
fi

if [ "$DECRYPT_PI" = true ]; then
    mkdir -p ~/.pi/agent
fi
