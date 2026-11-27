"""Shared self-deployment job state persistence and GitHub main cloning helpers."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from pathlib import Path
import subprocess
from typing import Any, Callable, TypeVar

from pydantic import BaseModel

from sandbox.apps._models import MAX_LAUNCH_LOG_LINES, utc_now_iso

ACTIVE_DEPLOY_STATUSES: frozenset[str] = frozenset({"queued", "cloning", "building", "deploying"})
STALE_DEPLOY_MINUTES = 20

_TDeployRecord = TypeVar("_TDeployRecord", bound=BaseModel)


def is_stale_active_deploy(record: Any) -> bool:
    """Returns True when an active deploy record has exceeded the stale timeout."""
    if getattr(record, "status", None) not in ACTIVE_DEPLOY_STATUSES:
        return False
    try:
        updated = datetime.fromisoformat(record.updated_at)
    except ValueError:
        return False
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    age_secs = (datetime.now(timezone.utc) - updated).total_seconds()
    return age_secs > STALE_DEPLOY_MINUTES * 60


def clone_latest_main(dest_dir: Path, *, org_name: str, gh_token: str) -> str:
    """Shallow-clones github.com/<org_name>/software-factory (main) and returns short commit SHA."""
    basic_b64 = base64.b64encode(f"x-access-token:{gh_token}".encode("utf-8")).decode("ascii")
    repo_url = f"https://github.com/{org_name}/software-factory.git"
    auth_cfg = f"http.https://github.com/.extraheader=AUTHORIZATION: basic {basic_b64}"
    clone_cmd = [
        "git",
        "-c",
        "credential.helper=",
        "-c",
        auth_cfg,
        "clone",
        "--depth",
        "1",
        "--branch",
        "main",
        "--single-branch",
        repo_url,
        str(dest_dir),
    ]
    res = subprocess.run(clone_cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(
            f"Failed cloning {org_name}/software-factory (main): {res.stderr.strip() or res.stdout.strip()}"
        )

    rev = subprocess.run(
        ["git", "-C", str(dest_dir), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if rev.returncode != 0 or not rev.stdout.strip():
        raise RuntimeError("Cloned repository did not yield a valid HEAD commit.")
    return rev.stdout.strip()


def read_full_head_commit(repo_dir: Path, fallback_short: str) -> str:
    """Resolves the full 40-char HEAD SHA when repo_dir is a Git checkout."""
    if not (repo_dir / ".git").exists():
        return fallback_short
    rev = subprocess.run(
        ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if rev.returncode == 0 and rev.stdout.strip():
        return rev.stdout.strip()
    return fallback_short


def list_deploy_jobs_unlocked(store: Any, subdir: str, model_cls: type[_TDeployRecord]) -> list[_TDeployRecord]:
    """Lists deploy records inside a store subdirectory sorted newest first."""
    deploys_dir = store.root_dir / subdir
    if not deploys_dir.is_dir():
        return []
    items: list[_TDeployRecord] = []
    for entry in deploys_dir.glob("*.json"):
        rec = store._read_model_file(entry, model_cls)
        if rec is not None:
            items.append(rec)
    items.sort(key=lambda item: item.created_at, reverse=True)
    return items


def create_deploy_job(
    store: Any,
    *,
    subdir: str,
    model_cls: type[_TDeployRecord],
    conflict_exc_cls: type[Exception],
    conflict_noun: str,
    build_record: Callable[[], _TDeployRecord],
) -> _TDeployRecord:
    """Persists a new queued deploy record if no non-stale active deploy is running."""
    deploys_dir = store.root_dir / subdir
    with store._lock:
        store._reload_volume()
        deploys_dir.mkdir(parents=True, exist_ok=True)
        for existing in list_deploy_jobs_unlocked(store, subdir, model_cls):
            if existing.status in ACTIVE_DEPLOY_STATUSES and not is_stale_active_deploy(existing):
                raise conflict_exc_cls(
                    f"{conflict_noun} '{existing.deploy_id}' is already {existing.status}."
                )
        record = build_record()
        path = deploys_dir / f"{store._validate_id(record.deploy_id)}.json"
        store._write_model_file(path, record)
        store._commit_volume()
        return record


def get_deploy_job(
    store: Any,
    *,
    subdir: str,
    model_cls: type[_TDeployRecord],
    deploy_id: str,
    reload: bool = True,
) -> _TDeployRecord | None:
    """Loads one deploy record by ID from a store subdirectory."""
    try:
        path = (store.root_dir / subdir) / f"{store._validate_id(deploy_id)}.json"
    except ValueError:
        return None
    return store._get_record(path, model_cls, reload=reload)


def get_latest_deploy_job(
    store: Any,
    *,
    subdir: str,
    model_cls: type[_TDeployRecord],
    reload: bool = True,
) -> _TDeployRecord | None:
    """Returns the most recent deploy record from a store subdirectory, if any."""
    with store._lock:
        if reload:
            store._reload_volume()
        items = list_deploy_jobs_unlocked(store, subdir, model_cls)
        return items[0] if items else None


def update_deploy_job(
    store: Any,
    *,
    subdir: str,
    model_cls: type[_TDeployRecord],
    deploy_id: str,
    missing_label: str,
    append_logs: list[str] | None = None,
    **updates: Any,
) -> _TDeployRecord:
    """Reloads, applies updates and bounded log appends to a deploy record, and commits."""
    path = (store.root_dir / subdir) / f"{store._validate_id(deploy_id)}.json"

    def _mutate(cur: _TDeployRecord) -> _TDeployRecord:
        merged = dict(updates)
        if append_logs:
            merged["logs"] = [*cur.logs, *append_logs][-MAX_LAUNCH_LOG_LINES:]
        merged.setdefault("updated_at", utc_now_iso())
        return cur.model_copy(update=merged)

    result = store._modify_record(path, model_cls, _mutate, f"{missing_label} '{deploy_id}' not found.")
    assert result is not None
    return result
