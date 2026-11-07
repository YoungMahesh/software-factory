"""Modal Sandbox Snapshot Registry.

Persists and manages metadata for captured filesystem snapshots using a named
modal.Dict ('sandbox-snapshots') with a local JSON file fallback.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any

import modal

logger = logging.getLogger(__name__)

SNAPSHOT_DICT_NAME = "sandbox-snapshots"
LOCAL_REGISTRY_FILE = Path.home() / ".modal" / "sandbox-snapshots.json"


def _get_local_registry_path() -> Path:
    """Returns local fallback JSON path and ensures parent directory exists."""
    LOCAL_REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    return LOCAL_REGISTRY_FILE


def _load_local_registry() -> dict[str, dict[str, Any]]:
    """Loads snapshots from local JSON file fallback."""
    path = _get_local_registry_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception as exc:
        logger.warning("Failed to parse local snapshot registry: %s", exc)
    return {}


def _save_local_registry(data: dict[str, dict[str, Any]]) -> None:
    """Saves snapshots to local JSON file fallback."""
    path = _get_local_registry_path()
    try:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to save local snapshot registry: %s", exc)


def _get_modal_dict(store_name: str = SNAPSHOT_DICT_NAME) -> modal.Dict | None:
    """Attempts to resolve the cloud modal.Dict; returns None on connection or auth failure."""
    try:
        return modal.Dict.from_name(store_name, create_if_missing=True)
    except Exception as exc:
        logger.debug("modal.Dict lookup failed (%s); falling back to local registry", exc)
        return None


def record_snapshot(
    image_id: str,
    sandbox_id: str,
    name: str = "",
    ttl_days: int = 30,
    is_vm: bool = False,
    profile: str | None = None,
    store_name: str = SNAPSHOT_DICT_NAME,
) -> dict[str, Any]:
    """Records metadata for a captured snapshot in the registry."""
    now_iso = datetime.now(timezone.utc).isoformat()
    record: dict[str, Any] = {
        "image_id": image_id,
        "sandbox_id": sandbox_id,
        "name": name.strip() if name else f"snapshot-{image_id[:10]}",
        "created_at": now_iso,
        "ttl_days": ttl_days,
        "ttl_seconds": ttl_days * 86400,
        "is_vm": is_vm,
        "profile": profile,
    }

    modal_dict = _get_modal_dict(store_name)
    if modal_dict is not None:
        try:
            modal_dict[image_id] = record
            return record
        except Exception as exc:
            logger.warning("Failed to write snapshot to modal.Dict: %s; saving locally", exc)

    local_data = _load_local_registry()
    local_data[image_id] = record
    _save_local_registry(local_data)
    return record


def list_snapshots(
    profile: str | None = None,
    store_name: str = SNAPSHOT_DICT_NAME,
) -> list[dict[str, Any]]:
    """Lists available snapshots sorted by creation date descending, optionally filtered by profile."""
    snapshots: list[dict[str, Any]] = []

    modal_dict = _get_modal_dict(store_name)
    if modal_dict is not None:
        try:
            for item in modal_dict.values():
                if isinstance(item, dict) and "image_id" in item:
                    snapshots.append(item)
        except Exception as exc:
            logger.warning("Failed reading snapshots from modal.Dict: %s", exc)

    if not snapshots:
        local_data = _load_local_registry()
        for item in local_data.values():
            if isinstance(item, dict) and "image_id" in item:
                snapshots.append(item)

    if profile and profile != "all":
        snapshots = [s for s in snapshots if s.get("profile") == profile or s.get("profile") is None]

    snapshots.sort(key=lambda s: s.get("created_at", ""), reverse=True)
    return snapshots


def get_snapshot(image_id: str, store_name: str = SNAPSHOT_DICT_NAME) -> dict[str, Any] | None:
    """Retrieves a single snapshot by image ID."""
    modal_dict = _get_modal_dict(store_name)
    if modal_dict is not None:
        try:
            val = modal_dict.get(image_id)
            if isinstance(val, dict):
                return val
        except Exception:
            pass

    local_data = _load_local_registry()
    return local_data.get(image_id)


def delete_snapshot(image_id: str, store_name: str = SNAPSHOT_DICT_NAME) -> bool:
    """Removes a snapshot record from registry; returns True if deleted."""
    deleted = False

    modal_dict = _get_modal_dict(store_name)
    if modal_dict is not None:
        try:
            if hasattr(modal_dict, "pop"):
                val = modal_dict.pop(image_id, None)
                if val is not None:
                    deleted = True
            elif image_id in modal_dict:
                del modal_dict[image_id]
                deleted = True
        except Exception as exc:
            logger.warning("Failed to delete snapshot %s from modal.Dict: %s", image_id, exc)

    local_data = _load_local_registry()
    if image_id in local_data:
        del local_data[image_id]
        _save_local_registry(local_data)
        deleted = True

    return deleted
