"""Modal multi-profile configuration and client management.

Discovers configured workspace profiles from MODAL_TOKENS in environment or ~/.modal.toml,
and supplies authenticated modal.Client instances scoped to specific profiles.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
import tomllib
from typing import Any

import modal

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path.home() / ".modal.toml"

_CLIENT_CACHE: dict[str, modal.Client] = {}


def get_config_path(override_path: Path | str | None = None) -> Path:
    """Returns the effective modal toml configuration file path."""
    if override_path is not None:
        return Path(override_path).expanduser().resolve()
    env_path = os.environ.get("MODAL_CONFIG_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return DEFAULT_CONFIG_PATH.expanduser().resolve()


def parse_modal_tokens_data(raw: str | Any) -> dict[str, dict[str, Any]]:
    """Parses a JSON string or list structure into profile configurations."""
    if not raw:
        return {}
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except Exception as exc:
            logger.warning("Failed to parse MODAL_TOKENS JSON: %s", exc)
            return {}
    elif isinstance(raw, list):
        data = raw
    else:
        return {}

    if not isinstance(data, list):
        return {}

    profiles: dict[str, dict[str, Any]] = {}
    for idx, entry in enumerate(data):
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or entry.get("profile") or f"profile-{idx+1}").strip()
        slug = re.sub(r"[^a-zA-Z0-9_-]", "-", name.lower().strip()).strip("-") or f"profile-{idx+1}"
        token_id = entry.get("token_id")
        token_secret = entry.get("token_secret")
        if token_id and token_secret:
            prof: dict[str, Any] = {
                "token_id": str(token_id),
                "token_secret": str(token_secret),
                "environment": str(entry.get("environment", "main")),
            }
            if entry.get("active") is True:
                prof["active"] = True
            profiles[slug] = prof
    return profiles


def parse_modal_tokens_env() -> dict[str, dict[str, Any]]:
    """Parses MODAL_TOKENS environment variable containing a JSON array of profile objects."""
    return parse_modal_tokens_data(os.environ.get("MODAL_TOKENS", ""))


def load_profiles_config(config_path: Path | str | None = None) -> dict[str, dict[str, Any]]:
    """Loads and parses profiles from MODAL_TOKENS env or modal configuration file."""
    if config_path is None:
        env_profiles = parse_modal_tokens_env()
        if env_profiles:
            return env_profiles

    path = get_config_path(config_path)
    if not path.is_file():
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        profiles: dict[str, dict[str, Any]] = {}
        for key, val in data.items():
            if isinstance(val, dict) and "token_id" in val:
                profiles[key] = dict(val)
        return profiles
    except Exception as exc:
        logger.warning("Failed to load modal config from %s: %s", path, exc)
        return {}


def get_active_profile_name(config_path: Path | str | None = None) -> str | None:
    """Determines the active profile name from environment or loaded profiles."""
    env_profile = os.environ.get("MODAL_PROFILE")
    if env_profile:
        return env_profile

    profiles = load_profiles_config(config_path)
    for name, data in profiles.items():
        if data.get("active") is True:
            return name

    # Fall back to first profile if none marked explicitly active
    if profiles:
        return next(iter(profiles.keys()))

    return None


def get_available_profiles(config_path: Path | str | None = None) -> list[dict[str, Any]]:
    """Lists configured profiles without exposing secrets."""
    profiles = load_profiles_config(config_path)
    active_name = get_active_profile_name(config_path)

    result: list[dict[str, Any]] = []
    for name, data in profiles.items():
        result.append({
            "name": name,
            "active": (name == active_name),
            "environment": data.get("environment", "main"),
        })

    return result


def get_profile_credentials(
    profile_name: str | None = None,
    config_path: Path | str | None = None,
) -> dict[str, str] | None:
    """Returns credentials dictionary containing token_id and token_secret for a profile."""
    profiles = load_profiles_config(config_path)
    target = profile_name or get_active_profile_name(config_path)
    if not target or target not in profiles:
        return None
    creds = profiles[target]
    token_id = creds.get("token_id")
    token_secret = creds.get("token_secret")
    if token_id and token_secret:
        return {"token_id": token_id, "token_secret": token_secret}
    return None


def get_client_for_profile(
    profile_name: str | None = None,
    config_path: Path | str | None = None,
    use_cache: bool = True,
) -> modal.Client:
    """Builds or retrieves a cached modal.Client for the given profile name."""
    active_profile = get_active_profile_name(config_path)
    target_profile = profile_name if profile_name and profile_name != "all" else active_profile

    cache_key = target_profile or "__default__"
    if use_cache and cache_key in _CLIENT_CACHE:
        return _CLIENT_CACHE[cache_key]

    profiles = load_profiles_config(config_path)

    if target_profile and target_profile in profiles:
        creds = profiles[target_profile]
        token_id = creds.get("token_id")
        token_secret = creds.get("token_secret")
        if token_id and token_secret:
            client = modal.Client.from_credentials(token_id, token_secret)
            if use_cache:
                _CLIENT_CACHE[cache_key] = client
            return client

    # Fallback to default client from environment
    client = modal.Client.from_env()
    if use_cache:
        _CLIENT_CACHE[cache_key] = client
    return client


def get_all_clients(
    config_path: Path | str | None = None,
    use_cache: bool = True,
) -> dict[str, modal.Client]:
    """Returns authenticated modal.Client instances for all configured profiles."""
    profiles = load_profiles_config(config_path)
    clients: dict[str, modal.Client] = {}

    for name in profiles:
        try:
            clients[name] = get_client_for_profile(name, config_path=config_path, use_cache=use_cache)
        except Exception as exc:
            logger.warning("Could not initialize client for profile %s: %s", name, exc)

    if not clients:
        try:
            clients["default"] = modal.Client.from_env()
        except Exception as exc:
            logger.warning("Could not initialize default modal client: %s", exc)

    return clients


def clear_client_cache() -> None:
    """Clears cached modal.Client instances."""
    _CLIENT_CACHE.clear()
