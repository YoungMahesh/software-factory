"""Factory sandbox job dispatch, status querying, cancellation, and SSE log streaming."""

import asyncio
import json
import queue as pyqueue

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from factory.ui.registry import JobRegistry, job_registry

router = APIRouter()


class LaunchJobRequest(BaseModel):
    repo: str = Field(..., description="Target repository name in Test Organization (e.g. 'test3')")
    feature: str | None = Field(None, description="Feature / milestone slug (e.g. 'slug-generator')")
    issue: str | None = Field(None, description="Optional ticket ID (e.g. '01' or '42')")
    model: str = Field("deepseek-v4.1-flash", description="Model identifier")
    vm: bool = Field(False, description="Launch in VM Sandbox with Docker support")
    dev: bool = Field(False, description="Launch in dev preview mode with port 3000 keep-alive")


def _get_registry(request: Request) -> JobRegistry:
    return getattr(request.app.state, "registry", job_registry)


@router.post("/api/jobs")
async def launch_job(req: LaunchJobRequest, request: Request):
    if not req.repo or not req.repo.strip():
        raise HTTPException(status_code=400, detail="Repository name is required.")

    feature = (req.feature or "").strip()
    issue = (req.issue or "").strip() or None

    if not feature:
        if issue:
            feature = f"issue-{issue}"
        else:
            raise HTTPException(status_code=400, detail="Feature / milestone slug or issue ID is required.")

    registry = _get_registry(request)
    job = registry.create_job(
        repo=req.repo,
        feature=feature,
        issue=issue,
        model=req.model,
        vm=req.vm,
        dev=req.dev,
    )
    registry.start_job(job.id)
    return job.to_dict()


@router.get("/api/jobs")
async def list_jobs(request: Request):
    registry = _get_registry(request)
    return {"jobs": registry.list_jobs()}


@router.get("/api/jobs/{job_id}")
async def get_job(job_id: str, request: Request):
    registry = _get_registry(request)
    job = registry.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return job.to_dict()


@router.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, request: Request):
    registry = _get_registry(request)
    success = registry.cancel_job(job_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Job '{job_id}' is not currently running or not found.",
        )
    return {"message": f"Job {job_id} cancelled.", "success": True}


@router.get("/api/jobs/{job_id}/stream")
async def stream_job(job_id: str, request: Request):
    registry = _get_registry(request)
    job = registry.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    q = registry.add_listener(job_id)
    if q is None:
        raise HTTPException(status_code=404, detail="Unable to subscribe to job events.")

    async def event_generator():
        try:
            # 1. Send initial sync snapshot
            init_payload = {
                "event": "init",
                "job": job.to_dict(),
                "backlog": job.logs,
                "events": job.events,
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
                    if job.status in ("SUCCESS", "FAILED", "CANCELLED") and q.empty():
                        break
                    await asyncio.sleep(0.2)
                    yield ": ping\n\n"

        finally:
            registry.remove_listener(job_id, q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
