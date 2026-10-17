"""Factory sandbox job dispatch, status querying, cancellation, and SSE log streaming."""

import asyncio
import json
import queue as pyqueue

from typing import Any

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


def _get_db(request: Request):
    db = getattr(request.app.state, "db", None)
    if db is not None:
        return db
    reg = _get_registry(request)
    if getattr(reg, "db", None) is not None:
        return reg.db
    try:
        from factory.ui.db import StudioDatabase
        return StudioDatabase()
    except Exception:
        return None


def _extract_failed_commands(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failed_commands: list[dict[str, Any]] = []
    allowed_stages = {"CODER", "VERIFIER"}

    for idx, evt in enumerate(events):
        evt_type = evt.get("type") or evt.get("event_type")
        if evt_type != "tool_result":
            continue

        raw_stage = evt.get("stage") or ""
        stage = raw_stage.upper()
        if stage not in allowed_stages:
            continue

        data = evt.get("data")
        if not isinstance(data, dict):
            data = evt

        tool_name = (data.get("toolName") or data.get("tool_name") or "").lower()
        if tool_name != "bash":
            continue

        exit_code_raw = data.get("exitCode") if data.get("exitCode") is not None else data.get("exit_code")
        is_error = bool(data.get("isError") or data.get("is_error") or False)

        if exit_code_raw is not None:
            try:
                exit_code = int(exit_code_raw)
            except (ValueError, TypeError):
                exit_code = 1 if is_error else 0
        else:
            exit_code = 1 if is_error else 0

        # Only isolate failed commands
        if exit_code == 0 and not is_error:
            continue

        args = data.get("args") if isinstance(data.get("args"), dict) else {}
        command = data.get("command") or args.get("command") or "bash"
        cwd = data.get("cwd") or args.get("cwd")
        duration_ms = data.get("durationMs") if data.get("durationMs") is not None else data.get("duration_ms")
        stdout = data.get("stdout") or ""
        stderr = data.get("stderr") or ""
        output = data.get("output") or stdout or stderr or ""
        tool_call_id = data.get("toolCallId") or data.get("tool_call_id") or evt.get("id") or f"failed-cmd-{idx}"
        timestamp = evt.get("created_at") or evt.get("timestamp")

        failed_commands.append({
            "id": str(tool_call_id),
            "command": command,
            "cwd": cwd,
            "stage": stage,
            "exit_code": exit_code,
            "exitCode": exit_code,
            "duration_ms": duration_ms,
            "durationMs": duration_ms,
            "stdout": stdout,
            "stderr": stderr,
            "output": output,
            "is_error": is_error or (exit_code != 0),
            "isError": is_error or (exit_code != 0),
            "timestamp": timestamp,
        })

    return failed_commands


@router.get("/api/jobs/{job_id}/failed-commands")
async def get_failed_commands(job_id: str, request: Request):
    registry = _get_registry(request)
    job = registry.get_job(job_id)
    db = _get_db(request)

    events: list[dict[str, Any]] = []
    job_found = False

    if job is not None:
        job_found = True
        events = list(job.events)

    if not events and db is not None:
        try:
            db_job = db.get_job(job_id)
            if db_job:
                job_found = True
            db_events = db.get_telemetry_events(job_id)
            if db_events:
                job_found = True
                events = db_events
        except Exception:
            pass

    if not job_found:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    failed_commands = _extract_failed_commands(events)
    return {
        "job_id": job_id,
        "total_failed": len(failed_commands),
        "failed_commands": failed_commands,
    }

