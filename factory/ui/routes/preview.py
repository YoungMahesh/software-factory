"""Preview sandbox launch, status, branch switching, and trunk synchronization."""

import asyncio
import concurrent.futures
import json
import queue as pyqueue
import re
import shlex
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from factory.ui.registry import (
    JobRegistry,
    job_registry,
    PreviewRegistry,
    preview_registry,
    PreviewState,
    PreviewStatus,
)

router = APIRouter()


class LaunchPreviewRequest(BaseModel):
    branch: str | None = Field(None, description="Optional target branch to serve (e.g. 'factory/<feature>' or 'main')")


class PreviewSyncRequest(BaseModel):
    branch: str | None = Field(None, description="Optional target branch to synchronize (defaults to active preview branch or main)")


class PreviewBranchRequest(BaseModel):
    branch: str = Field(..., description="Target branch to switch to")


UpdatePreviewBranchRequest = PreviewBranchRequest


def _get_registry(request: Request) -> JobRegistry:
    return getattr(request.app.state, "registry", job_registry)


def _get_preview_reg(request: Request) -> PreviewRegistry:
    return getattr(request.app.state, "preview_reg", preview_registry)


def _execute_in_sandbox_sync(
    active_sandbox: Any,
    clean_repo: str,
    bare_repo: str,
    target_branch: str,
    action_desc: str,
    preview_reg: PreviewRegistry,
) -> str | None:
    """Executes in-container branch checkout, remote fetch, and diff-aware package install."""
    sync_script = (
        f"cd /root/{bare_repo} && "
        f"git fetch origin {shlex.quote(target_branch)} && "
        'OLD_SHA=$(git rev-parse HEAD 2>/dev/null || echo "") && '
        f"(git checkout {shlex.quote(target_branch)} 2>/dev/null || git checkout -B {shlex.quote(target_branch)} origin/{shlex.quote(target_branch)}) && "
        f"git reset --hard origin/{shlex.quote(target_branch)} && "
        "git clean -fd && "
        'if [ -n "$OLD_SHA" ] && git diff --name-only "$OLD_SHA" HEAD | grep -E \'^(package\\.json|pnpm-lock\\.yaml)$\' >/dev/null; then '
        "pnpm install --prefer-offline; "
        "fi && "
        'echo "SYNC_COMMIT_SHA:$(git rev-parse --short HEAD)"'
    )

    preview_reg.append_log(
        clean_repo,
        f"🔄 [SYNC] {action_desc}...\n",
        flush=True,
    )

    proc = active_sandbox.exec("bash", "-c", sync_script)
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    def stream_pipe(reader, is_err=False):
        if reader is None:
            return
        try:
            for chunk in reader:
                text = chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else str(chunk)
                if is_err:
                    stderr_lines.append(text)
                else:
                    stdout_lines.append(text)
                for subline in text.splitlines(keepends=True):
                    if subline.startswith("SYNC_COMMIT_SHA:"):
                        continue
                    prefix = "❌ [SYNC ERROR] " if is_err else "🔄 [SYNC] "
                    preview_reg.append_log(clean_repo, f"{prefix}{subline}", flush=True)
        except Exception:
            pass

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f_out = executor.submit(stream_pipe, getattr(proc, "stdout", None), False)
        f_err = executor.submit(stream_pipe, getattr(proc, "stderr", None), True)
        concurrent.futures.wait([f_out, f_err])

    exit_code = 0
    if hasattr(proc, "wait"):
        try:
            exit_code = proc.wait()
        except TypeError:
            proc.wait(raise_on_termination=False)
            exit_code = getattr(proc, "returncode", 0)
    elif hasattr(proc, "returncode"):
        exit_code = proc.returncode

    if exit_code is None:
        exit_code = getattr(proc, "returncode", 0)

    if exit_code != 0:
        err_msg = "".join(stderr_lines).strip() or "".join(stdout_lines).strip() or f"Process exited with code {exit_code}"
        preview_reg.append_log(clean_repo, f"❌ [SYNC ERROR] {err_msg}\n", flush=True)
        raise HTTPException(
            status_code=400,
            detail=f"Trunk synchronization failed: {err_msg}",
        )

    commit_sha = None
    full_output = "".join(stdout_lines)
    match = re.search(r"SYNC_COMMIT_SHA:([0-9a-fA-F]+)", full_output)
    if match:
        commit_sha = match.group(1)
    else:
        sha_match = re.search(r"HEAD is now at ([0-9a-fA-F]+)", full_output)
        if sha_match:
            commit_sha = sha_match.group(1)

    preview_reg.update_branch(clean_repo, target_branch)
    preview_reg.append_log(
        clean_repo,
        f"🔄 [SYNC] Successfully synchronized with origin/{target_branch} (commit {commit_sha or 'HEAD'}).\n",
        flush=True,
    )
    preview_reg.broadcast_refresh(clean_repo)
    return commit_sha


@router.post("/api/repos/{repo}/preview", status_code=201)
async def launch_preview_endpoint(repo: str, request: Request, req: LaunchPreviewRequest | None = None):
    clean_repo = repo.strip()
    if not clean_repo:
        raise HTTPException(status_code=400, detail="Repository name is required.")
    preview_reg = _get_preview_reg(request)
    branch = req.branch if req else None
    preview = preview_reg.launch_preview(clean_repo, branch=branch)
    return JSONResponse(status_code=201, content=preview.to_dict())


@router.get("/api/repos/{repo}/preview")
async def get_preview_endpoint(repo: str, request: Request):
    clean_repo = repo.strip()
    if not clean_repo:
        raise HTTPException(status_code=400, detail="Repository name is required.")
    preview_reg = _get_preview_reg(request)
    preview = preview_reg.get_preview(clean_repo)
    if not preview:
        return PreviewState(repo=clean_repo).to_dict()
    return preview.to_dict()


@router.delete("/api/repos/{repo}/preview")
async def stop_preview_endpoint(repo: str, request: Request):
    clean_repo = repo.strip()
    if not clean_repo:
        raise HTTPException(status_code=400, detail="Repository name is required.")
    preview_reg = _get_preview_reg(request)
    stopped = await preview_reg.stop_preview(clean_repo)
    if not stopped:
        raise HTTPException(
            status_code=400,
            detail=f"No active running preview found for repository '{clean_repo}'.",
        )
    return {"message": f"Preview for {clean_repo} stopped.", "success": True, "repo": clean_repo}


@router.get("/api/repos/{repo}/preview/stream")
async def stream_preview_endpoint(repo: str, request: Request):
    clean_repo = repo.strip()
    if not clean_repo:
        raise HTTPException(status_code=400, detail="Repository name is required.")

    preview_reg = _get_preview_reg(request)
    preview = preview_reg.get_preview(clean_repo)
    if not preview:
        raise HTTPException(
            status_code=404,
            detail=f"No active preview found for repository '{clean_repo}'.",
        )

    q = preview_reg.add_listener(clean_repo)
    if q is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unable to subscribe to preview events for repository '{clean_repo}'.",
        )

    async def event_generator():
        try:
            # 1. Send initial sync snapshot
            init_payload = {
                "event": "init",
                "preview": preview.to_dict(),
                "backlog": list(preview.logs),
                "status": preview.status.value,
                "stage": preview.stage.value,
                "preview_url": preview.preview_url,
            }
            yield f"data: {json.dumps(init_payload)}\n\n"

            # 2. Stream real-time events as they arrive
            while True:
                if await request.is_disconnected():
                    break

                try:
                    event_data = q.get_nowait()
                    yield f"data: {json.dumps(event_data)}\n\n"
                except pyqueue.Empty:
                    if preview.status in ("STOPPED", "FAILED") and q.empty():
                        break
                    await asyncio.sleep(0.2)
                    yield ": ping\n\n"

        finally:
            preview_reg.remove_listener(clean_repo, q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/repos/{repo}/preview/sync")
async def sync_preview_endpoint(repo: str, request: Request, req: PreviewSyncRequest | None = None):
    clean_repo = repo.strip()
    bare_repo = clean_repo.split("/")[-1]

    registry = _get_registry(request)
    preview_reg = _get_preview_reg(request)

    # 1. Concurrency safety guard: strictly reject if an assembly line job is active
    if registry.is_job_active(clean_repo):
        raise HTTPException(
            status_code=409,
            detail="Cannot synchronize preview while an Assembly Line Pipeline job is active (RUNNING or QUEUED).",
        )

    preview = preview_reg.get_preview(clean_repo)
    target_branch = (req.branch.strip() if req and req.branch and req.branch.strip() else None)
    if not target_branch:
        target_branch = preview.branch if (preview and preview.branch) else "main"

    # 2. If Unified Studio Sandbox is actively SERVING, execute in-place sync
    active_sandbox, _ = preview_reg.get_active_sandbox(clean_repo)
    if active_sandbox is not None and preview is not None and preview.status == PreviewStatus.SERVING:
        try:
            commit_sha = _execute_in_sandbox_sync(
                active_sandbox,
                clean_repo,
                bare_repo,
                target_branch,
                f"Synchronizing Unified Studio Sandbox with origin/{target_branch}",
                preview_reg=preview_reg,
            )
            return {
                "success": True,
                "branch": target_branch,
                "commit": commit_sha,
                "updated": True,
                "message": f"Synchronized with origin/{target_branch}",
            }
        except HTTPException:
            raise
        except Exception as e:
            preview_reg.append_log(clean_repo, f"❌ [SYNC ERROR] {e}\n", flush=True)
            raise HTTPException(status_code=400, detail=f"Trunk synchronization failed: {e}")

    # 3. If preview sandbox is stopped or idle, record target branch in registry
    preview_reg.record_target_branch(clean_repo, target_branch)
    return {
        "success": True,
        "branch": target_branch,
        "commit": None,
        "updated": False,
        "message": f"Target branch set to '{target_branch}' for next preview launch",
    }


@router.post("/api/repos/{repo}/preview/branch")
async def switch_preview_branch_endpoint(repo: str, req: PreviewBranchRequest, request: Request):
    clean_repo = repo.strip()
    if not clean_repo:
        raise HTTPException(status_code=400, detail="Repository name is required.")

    bare_repo = clean_repo.split("/")[-1]
    target_branch = req.branch.strip() if req and req.branch else ""
    if not target_branch:
        raise HTTPException(status_code=400, detail="Branch name cannot be empty.")

    # Target branch format validation: must be 'main' or start with 'factory/'
    if not (target_branch == "main" or target_branch.startswith("factory/")):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid target branch '{target_branch}'. Target branch must be 'main' or start with 'factory/'.",
        )

    registry = _get_registry(request)
    preview_reg = _get_preview_reg(request)

    # Concurrency safety guard: cannot switch branches while an Assembly Line job is active
    if registry.is_job_active(clean_repo):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot change branch: an Assembly Line Pipeline job is currently active for {clean_repo}.",
        )

    preview = preview_reg.get_preview(clean_repo)
    active_sandbox, _ = preview_reg.get_active_sandbox(clean_repo)

    # Provisioning state guard: cannot switch in place while container is bootstrapping
    if preview and preview.status == PreviewStatus.PROVISIONING:
        raise HTTPException(
            status_code=409,
            detail=f"Unified Studio Sandbox for '{clean_repo}' is currently provisioning. Please wait until provisioning completes before switching branches.",
        )

    in_place = False
    commit_sha = None
    sb = active_sandbox if active_sandbox is not None else (preview.sandbox if (preview and preview.sandbox is not None and preview.status == PreviewStatus.SERVING) else None)
    if sb is not None and preview is not None and preview.status == PreviewStatus.SERVING:
        try:
            if target_branch == "main":
                commit_sha = _execute_in_sandbox_sync(
                    sb,
                    clean_repo,
                    bare_repo,
                    "main",
                    f"Switching branch to main and synchronizing Unified Studio Sandbox",
                    preview_reg=preview_reg,
                )
            else:
                await asyncio.to_thread(preview_reg.switch_preview_branch, clean_repo, target_branch)
            in_place = True
        except HTTPException:
            raise
        except Exception as e:
            preview_reg.append_log(clean_repo, f"❌ [SYNC ERROR] {e}\n", flush=True)
            raise HTTPException(status_code=400, detail=f"Branch switch failed: {e}")
    else:
        # Stopped / idle
        preview_reg.record_target_branch(clean_repo, target_branch)
        preview_reg.update_branch(clean_repo, target_branch)

    updated_preview = preview_reg.get_preview(clean_repo) or preview
    return {
        "repo": clean_repo,
        "branch": target_branch,
        "status": updated_preview.status.value if updated_preview else "IDLE",
        "preview_url": updated_preview.preview_url if updated_preview else None,
        "commit": commit_sha,
        "in_place": in_place,
        "updated": in_place,
        "success": True,
    }
