"""Background filesystem snapshot capture worker for Unified Studio Sandboxes."""

import logging
import os
import shlex
import threading
import time
from typing import Any

from factory.spawner import PreviewSpawnConfig

logger = logging.getLogger(__name__)

DEFAULT_SNAPSHOT_TTL_DAYS: int = 30
DEFAULT_SNAPSHOT_TTL_SECONDS: int = DEFAULT_SNAPSHOT_TTL_DAYS * 86400


def get_snapshot_ttl_seconds() -> int:
    """Returns configurable snapshot TTL in seconds from environment or default 30 days."""
    if "FACTORY_SNAPSHOT_TTL_SECONDS" in os.environ:
        try:
            return int(os.environ["FACTORY_SNAPSHOT_TTL_SECONDS"])
        except ValueError:
            pass
    try:
        days = int(os.environ.get("FACTORY_SNAPSHOT_TTL_DAYS", DEFAULT_SNAPSHOT_TTL_DAYS))
        return days * 86400
    except ValueError:
        return DEFAULT_SNAPSHOT_TTL_SECONDS


def _read_proc_stdout(proc: Any) -> str:
    """Safely extracts stdout from a sandbox process execution."""
    if not hasattr(proc, "stdout"):
        return ""
    stdout = proc.stdout
    if hasattr(stdout, "read"):
        res = stdout.read()
        return res.decode("utf-8", errors="replace") if isinstance(res, bytes) else str(res)
    elif hasattr(stdout, "__iter__"):
        chunks = []
        for chunk in stdout:
            chunks.append(chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else str(chunk))
        return "".join(chunks)
    return ""


def query_container_commit_sha(sandbox: Any, repo: str) -> str | None:
    """Queries current git commit HEAD inside the sandbox workspace."""
    clean_repo = repo.strip()
    bare_repo = clean_repo.split("/")[-1]
    workspace = f"/root/{bare_repo}"
    exec_cmd = f"git -C {shlex.quote(workspace)} rev-parse HEAD"

    try:
        proc = sandbox.exec("bash", "-c", exec_cmd)
        out = _read_proc_stdout(proc).strip()
        if hasattr(proc, "wait"):
            try:
                exit_code = proc.wait()
            except TypeError:
                proc.wait(raise_on_termination=False)
                exit_code = getattr(proc, "returncode", 0)
        else:
            exit_code = getattr(proc, "returncode", 0)

        if exit_code == 0 and out:
            first_line = out.splitlines()[0].strip()
            if len(first_line) == 40 and all(c in "0123456789abcdefABCDEF" for c in first_line):
                return first_line
    except Exception as e:
        logger.warning("Failed to query commit SHA for %s in sandbox: %s", repo, e)

    return None


def is_snapshot_needed(db: Any, repo: str, commit_sha: str | None) -> bool:
    """Determines if a new snapshot needs to be captured for the repository."""
    if db is None:
        return True
    try:
        meta = db.get_snapshot_metadata(repo)
        if meta and meta.get("snapshot_image_id"):
            if commit_sha and meta.get("snapshot_commit_sha") == commit_sha:
                return False
    except Exception as e:
        logger.warning("Error checking existing snapshot metadata for %s: %s", repo, e)
    return True


def capture_snapshot_for_preview(
    preview: Any,
    db: Any = None,
    ttl_seconds: int | None = None,
) -> str | None:
    """Synchronously executes sync and snapshot_filesystem for an active preview."""
    sandbox = getattr(preview, "sandbox", None)
    if sandbox is None:
        logger.debug("Cannot capture snapshot for %s: sandbox is None", preview.repo)
        return None

    repo = preview.repo
    logger.info("Initiating filesystem snapshot capture for preview %s...", repo)
    effective_ttl = ttl_seconds if ttl_seconds is not None else get_snapshot_ttl_seconds()

    try:
        commit_sha = query_container_commit_sha(sandbox, repo)
        if not is_snapshot_needed(db, repo, commit_sha):
            logger.info("Snapshot for %s is already up-to-date at commit %s", repo, commit_sha)
            return None

        # 1. Flush filesystem buffers inside container
        try:
            sync_proc = sandbox.exec("sync")
            if hasattr(sync_proc, "wait"):
                try:
                    sync_proc.wait()
                except TypeError:
                    sync_proc.wait(raise_on_termination=False)
        except Exception as sync_err:
            logger.warning("Filesystem sync error on preview %s (continuing): %s", repo, sync_err)

        # 2. Invoke snapshot_filesystem with retention
        snapshot_image = sandbox.snapshot_filesystem(ttl=effective_ttl)
        image_id = getattr(snapshot_image, "object_id", None) or str(snapshot_image)

        captured_at = time.time()
        preview.snapshot_image_id = image_id
        preview.snapshot_commit_sha = commit_sha
        preview.snapshot_captured_at = captured_at

        # 3. Persist snapshot metadata to Studio Database
        if db is not None:
            try:
                db.save_snapshot_metadata(
                    repo=repo,
                    snapshot_image_id=image_id,
                    snapshot_commit_sha=commit_sha or "",
                    captured_at=captured_at,
                )
            except Exception as db_err:
                logger.warning("Failed to persist snapshot metadata for %s: %s", repo, db_err)

        logger.info("Successfully captured filesystem snapshot %s for %s", image_id, repo)
        return image_id
    except Exception as e:
        # Errors in snapshot capture must not disrupt the running preview
        logger.warning("Snapshot capture failed for %s (preview continues serving): %s", repo, e)
        return None


def trigger_background_snapshot(
    preview: Any,
    db: Any = None,
    ttl_seconds: int | None = None,
) -> threading.Thread | None:
    """Dispatches background snapshot capture worker thread if not already running."""
    if getattr(preview, "sandbox", None) is None:
        return None

    if getattr(preview, "_snapshot_in_progress", False):
        return None

    effective_ttl = ttl_seconds if ttl_seconds is not None else get_snapshot_ttl_seconds()

    def worker():
        try:
            preview._snapshot_in_progress = True
            capture_snapshot_for_preview(preview, db=db, ttl_seconds=effective_ttl)
        finally:
            preview._snapshot_in_progress = False

    thread = threading.Thread(
        target=worker,
        daemon=True,
        name=f"snapshot-{preview.repo}",
    )
    preview._snapshot_thread = thread
    thread.start()
    return thread


def resolve_snapshot_image_id(db: Any, repo: str, preview: Any = None) -> str | None:
    """Checks DB and preview state for an existing snapshot image ID."""
    clean_repo = repo.strip()
    if db is not None:
        try:
            meta = db.get_snapshot_metadata(clean_repo)
            if meta and meta.get("snapshot_image_id"):
                return meta["snapshot_image_id"]
        except Exception as e:
            logger.warning("Failed to query snapshot metadata for %s: %s", clean_repo, e)
    if preview is not None:
        return getattr(preview, "snapshot_image_id", None)
    return None


def spawn_preview_sandbox_with_fallback(
    create_preview_fn: Any,
    repo: str,
    branch: str,
    db: Any = None,
    preview: Any = None,
    on_log: Any = None,
) -> tuple[Any, str]:
    """Attempts fast-path snapshot sandbox instantiation with graceful fallback to base image build."""
    clean_repo = repo.strip()
    snapshot_id = resolve_snapshot_image_id(db, clean_repo, preview)

    if snapshot_id:
        try:
            if on_log:
                on_log(f"⚡ [PREVIEW] Fast-path cold start: attempting snapshot resumption from {snapshot_id}...\n")
            logger.info("Attempting fast-path preview launch from snapshot %s for %s", snapshot_id, clean_repo)
            config = PreviewSpawnConfig(
                repo=clean_repo,
                branch=branch,
                testing=True,
                from_snapshot=snapshot_id,
                snapshot_resume=True,
            )
            return create_preview_fn(config)
        except Exception as snap_err:
            msg = f"⚠️ [PREVIEW] Snapshot resumption failed ({snap_err}); falling back to base image build...\n"
            if on_log:
                on_log(msg)
            logger.warning("Snapshot resumption failed for %s (image %s): %s; falling back to clean build", clean_repo, snapshot_id, snap_err)

    if on_log:
        on_log(f"🔨 [PREVIEW] Building base image and provisioning Unified Studio Sandbox for {clean_repo} ({branch})...\n")
    config = PreviewSpawnConfig(repo=clean_repo, branch=branch, testing=True)
    return create_preview_fn(config)
