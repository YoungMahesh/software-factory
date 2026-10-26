"""Background filesystem snapshot capture worker for Unified Studio Sandboxes."""

import logging
import shlex
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_SNAPSHOT_TTL_SECONDS: int = 30 * 86400  # 30 days


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
    ttl_seconds: int = DEFAULT_SNAPSHOT_TTL_SECONDS,
) -> str | None:
    """Synchronously executes sync and snapshot_filesystem for an active preview."""
    sandbox = getattr(preview, "sandbox", None)
    if sandbox is None:
        logger.debug("Cannot capture snapshot for %s: sandbox is None", preview.repo)
        return None

    repo = preview.repo
    logger.info("Initiating filesystem snapshot capture for preview %s...", repo)

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

        # 2. Invoke snapshot_filesystem with 30-day retention
        snapshot_image = sandbox.snapshot_filesystem(ttl=ttl_seconds)
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
    ttl_seconds: int = DEFAULT_SNAPSHOT_TTL_SECONDS,
) -> threading.Thread | None:
    """Dispatches background snapshot capture worker thread if not already running."""
    if getattr(preview, "sandbox", None) is None:
        return None

    if getattr(preview, "_snapshot_in_progress", False):
        return None

    def worker():
        try:
            preview._snapshot_in_progress = True
            capture_snapshot_for_preview(preview, db=db, ttl_seconds=ttl_seconds)
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
