"""Modal Sandbox Snapshot Registry and Lifecycle Manager.

Persists and manages metadata for captured filesystem snapshots using a named
modal.Dict ('sandbox-snapshots') with a local JSON file fallback, and provides
the canonical capture_sandbox_snapshot lifecycle seam.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any

import modal

from sandbox.config import DEFAULT_SNAPSHOT_TIMEOUT

logger = logging.getLogger(__name__)

SNAPSHOT_DICT_NAME = "sandbox-snapshots"
LOCAL_REGISTRY_FILE = Path.home() / ".modal" / "sandbox-snapshots.json"


@dataclass(frozen=True)
class SnapshotResult:
    sandbox_id: str
    image_id: str
    ttl_days: int
    ttl_seconds: int
    terminated: bool
    name: str = ""
    is_vm: bool = False
    profile: str | None = None
    software_factory_commit: str | None = None
    software_factory_dirty: str | None = None

    def to_response(self) -> Any:
        from sandbox.core import SnapshotResponse

        return SnapshotResponse(
            sandbox_id=self.sandbox_id,
            image_id=self.image_id,
            ttl_days=self.ttl_days,
            ttl_seconds=self.ttl_seconds,
            terminated=self.terminated,
        )


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
    software_factory_commit: str | None = None,
    software_factory_dirty: str | None = None,
) -> dict[str, Any]:
    """Records metadata for a captured snapshot in the registry."""
    now_iso = datetime.now(timezone.utc).isoformat()
    if software_factory_commit is None:
        try:
            from sandbox.launcher import resolve_host_software_factory_provenance

            prov = resolve_host_software_factory_provenance()
            software_factory_commit = prov.get("SOFTWARE_FACTORY_COMMIT_SHORT") or prov.get("SOFTWARE_FACTORY_COMMIT")
            if software_factory_dirty is None:
                software_factory_dirty = prov.get("SOFTWARE_FACTORY_DIRTY")
        except Exception:
            pass

    record: dict[str, Any] = {
        "image_id": image_id,
        "sandbox_id": sandbox_id,
        "name": name.strip() if name else f"snapshot-{image_id[:10]}",
        "created_at": now_iso,
        "ttl_days": ttl_days,
        "ttl_seconds": ttl_days * 86400,
        "is_vm": is_vm,
        "profile": profile,
        "software_factory_commit": software_factory_commit,
        "software_factory_dirty": software_factory_dirty or "0",
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


def capture_sandbox_snapshot(
    sandbox_id: str,
    ttl_days: int = 30,
    terminate: bool = False,
    name: str = "",
    profile: str | None = None,
    client: modal.Client | None = None,
    timeout: int = DEFAULT_SNAPSHOT_TIMEOUT,
    store_name: str = SNAPSHOT_DICT_NAME,
    echo: bool = False,
) -> SnapshotResult:
    """Flushes buffers, captures a filesystem snapshot, records it in the registry, and optionally terminates."""
    if echo:
        print(f"🔄 Flushing filesystem buffers inside sandbox {sandbox_id}...")

    target_client = client
    target_profile = profile
    if target_client is None and target_profile:
        try:
            from sandbox.profiles import get_client_for_profile

            target_client = get_client_for_profile(target_profile)
        except Exception:
            target_client = None
    elif target_client is None and not echo:
        try:
            from sandbox.profiles import get_all_clients

            for prof_name, cli in get_all_clients().items():
                try:
                    sb_probe = modal.Sandbox.from_id(sandbox_id, client=cli)
                    sb_probe.poll()
                    target_client = cli
                    target_profile = prof_name
                    break
                except Exception:
                    pass
        except Exception:
            pass

    sandbox = (
        modal.Sandbox.from_id(sandbox_id, client=target_client)
        if target_client
        else modal.Sandbox.from_id(sandbox_id)
    )
    sync_proc = sandbox.exec("sync")
    sync_proc.wait()

    is_vm = False
    try:
        vm_proc = sandbox.exec("sh", "-c", "[ -S /var/run/docker.sock ] || [ -f /swapfile ]")
        if vm_proc.wait() == 0:
            is_vm = True
    except Exception:
        is_vm = False

    if is_vm and echo:
        print(
            "⚠️  Notice: VM Sandbox detected. Mounted volumes and Docker daemon storage "
            "(/var/lib/docker) are ephemeral and not persisted in root filesystem snapshots."
        )

    ttl_seconds = ttl_days * 86400
    if echo:
        print(f"📸 Capturing filesystem snapshot (retention: {ttl_days} days, timeout: {timeout}s)...")
    snapshot_image = sandbox.snapshot_filesystem(timeout=timeout, ttl=ttl_seconds)
    image_id = snapshot_image.object_id

    record: dict[str, Any] | None = None
    try:
        record = record_snapshot(
            image_id=image_id,
            sandbox_id=sandbox_id,
            name=name,
            ttl_days=ttl_days,
            is_vm=is_vm,
            profile=target_profile,
            store_name=store_name,
        )
    except Exception as exc:
        logger.warning("Failed to record snapshot %s in registry: %s", image_id, exc)

    if echo:
        vm_flag = " --vm" if is_vm else ""
        print("\n" + "=" * 60)
        print("📸  Filesystem Snapshot Captured!")
        print(f"  • Sandbox ID:  {sandbox_id}")
        print(f"  • Image ID:    {image_id}")
        print(f"  • Retention:   {ttl_days} days ({ttl_seconds}s)")
        print(f"  • Resume:      modal-sandbox --from-snapshot {image_id} --name resumed-sandbox{vm_flag}")
        print("=" * 60 + "\n")

    if terminate:
        if echo:
            print(f"🧹 Terminating sandbox {sandbox_id}...")
        sandbox.terminate()
        if echo:
            print(f"✅ Sandbox {sandbox_id} terminated.")
    elif echo:
        print(f"ℹ️  Sandbox {sandbox_id} remains running (non-destructive snapshot).")

    return SnapshotResult(
        sandbox_id=sandbox_id,
        image_id=image_id,
        ttl_days=ttl_days,
        ttl_seconds=ttl_seconds,
        terminated=terminate,
        name=record.get("name", name) if record else name,
        is_vm=is_vm,
        profile=target_profile,
        software_factory_commit=record.get("software_factory_commit") if record else None,
        software_factory_dirty=record.get("software_factory_dirty") if record else None,
    )
