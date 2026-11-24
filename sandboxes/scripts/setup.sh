#!/usr/bin/env bash
set -euo pipefail

SETUP_MODAL=false
SETUP_T3=false

while [ "$#" -gt 0 ]; do
    case "$1" in
        --modal)
            SETUP_MODAL=true
            shift
            ;;
        --t3)
            SETUP_T3=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--modal] [--t3]"
            exit 0
            ;;
        *)
            echo "ERROR: Unknown option: $1" >&2
            echo "Usage: $0 [--modal] [--t3]" >&2
            exit 1
            ;;
    esac
done

if [ "$SETUP_MODAL" = true ]; then
    python3 -c '
import json, os, re

tokens_raw = os.environ.get("MODAL_TOKENS", "[]")
target_profile = os.environ.get("MODAL_PROFILE", "").strip()

try:
    parsed_tokens = json.loads(tokens_raw)
except Exception:
    parsed_tokens = []

profiles = []
if isinstance(parsed_tokens, list):
    for idx, entry in enumerate(parsed_tokens):
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or entry.get("profile") or f"profile-{idx+1}").strip()
        slug = re.sub(r"[^a-zA-Z0-9_-]", "-", name).strip("-") or f"profile-{idx+1}"
        token_id = entry.get("token_id")
        token_secret = entry.get("token_secret")
        env_name = str(entry.get("environment", "main"))
        is_active = bool(entry.get("active"))
        if token_id and token_secret:
            profiles.append({
                "slug": slug,
                "token_id": str(token_id),
                "token_secret": str(token_secret),
                "environment": env_name,
                "active": is_active
            })

if profiles:
    active_slug = None
    if target_profile and any(p["slug"] == target_profile for p in profiles):
        active_slug = target_profile
    else:
        for p in profiles:
            if p["active"]:
                active_slug = p["slug"]
                break
        if not active_slug:
            active_slug = profiles[0]["slug"]

    toml_path = os.path.expanduser("~/.modal.toml")
    lines = []
    for p in profiles:
        slug = p["slug"]
        tid = p["token_id"]
        tsec = p["token_secret"]
        env = p["environment"]
        lines.append(f"[{slug}]")
        lines.append(f"token_id = \"{tid}\"")
        lines.append(f"token_secret = \"{tsec}\"")
        if env:
            lines.append(f"environment = \"{env}\"")
        if slug == active_slug:
            lines.append("active = true")
        lines.append("")

    with open(toml_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    os.chmod(toml_path, 0o600)
' 2>/dev/null || true
fi

if [ "$SETUP_T3" = true ]; then
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

if [ "$SETUP_T3" = true ]; then
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

        oauth_token_data = {
            "token": {
                "access_token": "placeholder",
                "token_type": "Bearer",
                "refresh_token": refresh_token,
                "expiry": "2020-01-01T00:00:00Z"
            },
            "auth_method": "consumer"
        }

        profile_dir = os.path.expanduser("~/.gemini/antigravity-cli/profiles")
        os.makedirs(profile_dir, mode=0o700, exist_ok=True)
        profile_path = os.path.join(profile_dir, slug)
        with open(profile_path, "w") as pf:
            json.dump(oauth_token_data, pf, indent=2)
        os.chmod(profile_path, 0o600)

        if is_primary:
            primary_path = os.path.expanduser("~/.gemini/antigravity-cli/antigravity-oauth-token")
            with open(primary_path, "w") as pf:
                json.dump(oauth_token_data, pf, indent=2)
            os.chmod(primary_path, 0o600)

        for d in target_dirs:
            os.makedirs(d, mode=0o700, exist_ok=True)
            tok_file = os.path.join(d, "acp_token.json")
            set_file = os.path.join(d, "settings.json")
            oauth_file = os.path.join(d, "antigravity-oauth-token")
            with open(tok_file, "w") as fp:
                json.dump(acp_token, fp, indent=2)
            os.chmod(tok_file, 0o600)
            with open(set_file, "w") as fp:
                json.dump(acp_settings, fp, indent=2)
            os.chmod(set_file, 0o600)
            with open(oauth_file, "w") as fp:
                json.dump(oauth_token_data, fp, indent=2)
            os.chmod(oauth_file, 0o600)
            cache_sub = os.path.join(d, "cache")
            os.makedirs(cache_sub, mode=0o700, exist_ok=True)
            with open(os.path.join(cache_sub, "acp-auth-state.json"), "w") as fp:
                json.dump({"methodId": "oauth-personal"}, fp)
            with open(os.path.join(cache_sub, "onboarding.json"), "w") as fp:
                json.dump({"consumerOnboardingComplete": False, "enterpriseOnboardingComplete": False, "onboardingComplete": False}, fp)

        settings["providerInstances"][instance_id] = {
            "driver": "antigravity",
            "displayName": display_name,
            "enabled": True
        }
        configured_antigravity.append(instance_id)

        t3_cache_file = os.path.join(t3_cache_dir, f"{instance_id}.json")
        models_data = [
            {
                "slug": "gemini-3.8-flash",
                "name": "Gemini 3.8 Flash",
                "isCustom": False,
                "isDefault": True,
                "aliases": [f"{instance_id}-default", "gemini-3.8-flash-high"],
                "capabilities": {
                    "optionDescriptors": [
                        {
                            "id": "thought_level",
                            "label": "Thinking Level",
                            "type": "select",
                            "options": [
                                {"id": "low", "label": "Low"},
                                {"id": "medium", "label": "Medium"},
                                {"id": "high", "label": "High"}
                            ],
                            "currentValue": "high",
                            "role": "reasoning"
                        }
                    ]
                }
            },
            {
                "slug": "claude-sonnet-4-6",
                "name": "Claude Sonnet 4.6 (Thinking)",
                "isCustom": False,
                "capabilities": {
                    "optionDescriptors": [
                        {
                            "id": "thought_level",
                            "label": "Thinking Level",
                            "type": "select",
                            "options": [
                                {"id": "low", "label": "Low"},
                                {"id": "medium", "label": "Medium"},
                                {"id": "high", "label": "High"}
                            ],
                            "role": "reasoning"
                        }
                    ]
                }
            },
            {
                "slug": "claude-opus-4-6-thinking",
                "name": "Claude Opus 4.6 (Thinking)",
                "isCustom": False,
                "capabilities": {
                    "optionDescriptors": [
                        {
                            "id": "thought_level",
                            "label": "Thinking Level",
                            "type": "select",
                            "options": [
                                {"id": "low", "label": "Low"},
                                {"id": "medium", "label": "Medium"},
                                {"id": "high", "label": "High"}
                            ],
                            "role": "reasoning"
                        }
                    ]
                }
            },
            {
                "slug": "gpt-oss-120b-medium",
                "name": "GPT-OSS 120B (Medium)",
                "isCustom": False,
                "capabilities": {
                    "optionDescriptors": [
                        {
                            "id": "thought_level",
                            "label": "Thinking Level",
                            "type": "select",
                            "options": [
                                {"id": "low", "label": "Low"},
                                {"id": "medium", "label": "Medium"},
                                {"id": "high", "label": "High"}
                            ],
                            "role": "reasoning"
                        }
                    ]
                }
            }
        ]
        cache_data = {
            "displayName": display_name,
            "showInteractionModeToggle": False,
            "supportedRuntimeModes": [
                "approval-required",
                "auto-accept-edits",
                "auto",
                "full-access"
            ],
            "enabled": True,
            "installed": True,
            "version": "1.5.15",
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
            "models": models_data,
            "slashCommands": [],
            "skills": [],
            "supportsConversationRollback": True,
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
        "enabled": bool(os.environ.get("CODEX_RUNTIME_INSTALLED"))
    }

default_agy_instance = configured_antigravity[0] if configured_antigravity else None
if default_agy_instance:
    model_sel = {
        "instanceId": default_agy_instance,
        "model": "gemini-3.8-flash-low"
    }
    if not settings.get("sourceControlWriterModelSelection") or (settings.get("sourceControlWriterModelSelection", {}).get("instanceId") == "codex" and not settings["providerInstances"]["codex"]["enabled"]):
        settings["sourceControlWriterModelSelection"] = model_sel
    if not settings.get("textGenerationModelSelection") or (settings.get("textGenerationModelSelection", {}).get("instanceId") == "codex" and not settings["providerInstances"]["codex"]["enabled"]):
        settings["textGenerationModelSelection"] = model_sel

with open(t3_settings_path, "w") as fp:
    json.dump(settings, fp, indent=2)
os.chmod(t3_settings_path, 0o644)
' 2>/dev/null || true
    fi
fi
