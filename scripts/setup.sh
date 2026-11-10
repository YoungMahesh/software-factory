#!/usr/bin/env bash
set -euo pipefail

SETUP_MODAL=false
SETUP_AGY=false
SETUP_T3=false
SETUP_OPENCODE=false
SETUP_PI=false

while [ "$#" -gt 0 ]; do
    case "$1" in
        --modal)
            SETUP_MODAL=true
            shift
            ;;
        --agy)
            SETUP_AGY=true
            shift
            ;;
        --t3)
            SETUP_T3=true
            shift
            ;;
        --opencode)
            SETUP_OPENCODE=true
            shift
            ;;
        --pi)
            SETUP_PI=true
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

if [ "$SETUP_MODAL" = true ]; then
    if [ -n "${MODAL_TOKEN_ID:-}" ] && [ -n "${MODAL_TOKEN_SECRET:-}" ]; then
        mkdir -p ~/.modal
        cat << EOF > ~/.modal.toml
[default]
token_id = "$MODAL_TOKEN_ID"
token_secret = "$MODAL_TOKEN_SECRET"
EOF
        chmod 600 ~/.modal.toml
    fi
fi

if [ "$SETUP_OPENCODE" = true ] || [ "$SETUP_PI" = true ]; then
    if [ -n "${OPENCODE_GO_API_KEY:-}" ]; then
        mkdir -p ~/.config/opencode
        cat << EOF > ~/.config/opencode/opencode.env
OPENCODE_GO_API_KEY=$OPENCODE_GO_API_KEY
EOF
        chmod 600 ~/.config/opencode/opencode.env

        if [ -w /etc/environment ]; then
            grep -qxF "OPENCODE_GO_API_KEY=$OPENCODE_GO_API_KEY" /etc/environment 2>/dev/null || echo "OPENCODE_GO_API_KEY=$OPENCODE_GO_API_KEY" >> /etc/environment
        fi
        grep -qxF "export OPENCODE_GO_API_KEY=\"$OPENCODE_GO_API_KEY\"" ~/.bashrc 2>/dev/null || echo "export OPENCODE_GO_API_KEY=\"$OPENCODE_GO_API_KEY\"" >> ~/.bashrc
    fi
fi

if [ "$SETUP_AGY" = true ] || [ "$SETUP_T3" = true ] || [ "$SETUP_OPENCODE" = true ]; then
    if command -v python3 >/dev/null 2>&1; then
        python3 -c '
import hashlib, json, os, re

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

t3_cache_dir = os.path.expanduser("~/.t3/caches")
os.makedirs(t3_cache_dir, mode=0o755, exist_ok=True)

# Parse ANTIGRAVITY_TOKENS JSON array of objects
tokens_raw = os.environ.get("ANTIGRAVITY_TOKENS", "[]")
try:
    parsed_tokens = json.loads(tokens_raw)
except Exception:
    parsed_tokens = []

accounts = []
if isinstance(parsed_tokens, list):
    for idx, entry in enumerate(parsed_tokens):
        if isinstance(entry, dict):
            name = entry.get("name") or f"Account {idx+1}"
            tok = entry.get("token") or entry.get("refresh_token") or ""
        elif isinstance(entry, str):
            name = f"Account {idx+1}"
            tok = entry
        else:
            continue
        if not tok:
            continue
        slug = re.sub(r"[^a-zA-Z0-9_-]", "-", name.lower().strip()).strip("-") or f"acc{idx+1}"
        instance_id = "antigravity" if idx == 0 else f"antigravity-{slug}"
        is_primary = (idx == 0)
        accounts.append((instance_id, name, slug, tok, is_primary))

configured_antigravity = []
for instance_id, display_name, slug, refresh_token, is_primary in accounts:
    try:
        profile_dir = os.path.expanduser("~/.gemini/antigravity-cli/profiles")
        os.makedirs(profile_dir, mode=0o700, exist_ok=True)
        profile_path = os.path.join(profile_dir, slug)
        tok_data = {"token": {"refresh_token": refresh_token}}
        with open(profile_path, "w") as pf:
            json.dump(tok_data, pf, indent=2)
        os.chmod(profile_path, 0o600)

        if is_primary:
            primary_path = os.path.expanduser("~/.gemini/antigravity-cli/antigravity-oauth-token")
            with open(primary_path, "w") as pf:
                json.dump(tok_data, pf, indent=2)
            os.chmod(primary_path, 0o600)

        acp_settings = {"auth": {"type": "oauth-personal"}}
        t3_hash = hashlib.sha256(instance_id.encode("utf-8")).hexdigest()
        target_dirs = [os.path.expanduser(f"~/.t3/userdata/providers/antigravity/{t3_hash}/antigravity-acp")]
        if is_primary:
            target_dirs.append(os.path.expanduser("~/.gemini/antigravity-acp"))

        existing_tok = {}
        for candidate_dir in target_dirs + [os.path.expanduser("~/.gemini/antigravity-acp")]:
            candidate_file = os.path.join(candidate_dir, "acp_token.json")
            if os.path.exists(candidate_file):
                try:
                    with open(candidate_file, "r") as fp:
                        c_data = json.load(fp)
                        if c_data.get("client_id") and c_data.get("client_id") != "dummy-client-id.apps.googleusercontent.com":
                            existing_tok = c_data
                            break
                except Exception:
                    pass

        client_id = (
            os.environ.get("ANTIGRAVITY_CLIENT_ID")
            or os.environ.get("GOOGLE_CLIENT_ID")
            or existing_tok.get("client_id")
            or "dummy-client-id.apps.googleusercontent.com"
        )
        client_secret = (
            os.environ.get("ANTIGRAVITY_CLIENT_SECRET")
            or os.environ.get("GOOGLE_CLIENT_SECRET")
            or existing_tok.get("client_secret")
            or "dummy-client-secret"
        )

        acp_token = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "token_uri": "https://oauth2.googleapis.com/token",
            "scopes": [
                "https://www.googleapis.com/auth/cloud-platform",
                "https://www.googleapis.com/auth/userinfo.email",
                "https://www.googleapis.com/auth/aicode"
            ]
        }
        if existing_tok.get("project_id"):
            acp_token["project_id"] = existing_tok["project_id"]
        elif os.environ.get("ANTIGRAVITY_PROJECT_ID"):
            acp_token["project_id"] = os.environ.get("ANTIGRAVITY_PROJECT_ID")

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

# OpenCode provider in T3
has_opencode = bool(os.environ.get("OPENCODE_GO_API_KEY"))
opencode_env_path = os.path.expanduser("~/.config/opencode/opencode.env")
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
    opencode_bin = "/root/.opencode/bin/opencode" if os.path.exists("/root/.opencode/bin/opencode") else os.path.expanduser("~/.opencode/bin/opencode")
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

default_agy_instance = configured_antigravity[0] if configured_antigravity else None
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

if [ "$SETUP_PI" = true ]; then
    mkdir -p ~/.pi/agent
fi
