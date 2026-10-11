"""FastAPI Web Application for Factory Testing Console.

Serves the interactive testing dashboard, REST endpoints for repo and
issue discovery, and Server-Sent Events (SSE) for live terminal streaming.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from factory.ui.auth import BasicAuthMiddleware
from factory.ui.github import (
    DEFAULT_TEST_ORG,
    commit_approved_adr_to_branch,
    fetch_repo_issue,
    fetch_repo_issues,
    fetch_repo_milestones_and_issues,
    fetch_repo_scratch_metadata,
    fetch_test_org_repos,
    fetch_test_org_repos_detailed,
    instantiate_repo_from_template,
    RepoCreationError,
    resolve_or_create_milestone,
    synthesize_and_create_issue,
    validate_github_repo_name,
)
from factory.ui.db import StudioDatabase
from factory.ui.grill import GrillingAssistant
from factory.ui.guard import evaluate_prompt_intent
from factory.ui.registry import (
    JobRegistry,
    job_registry,
    PreviewRegistry,
    preview_registry,
    PreviewState,
    PreviewStatus,
)

STATIC_DIST_DIR = Path(__file__).resolve().parent / "static" / "dist"


class LaunchPreviewRequest(BaseModel):
    branch: str | None = Field(None, description="Optional target branch to serve (e.g. 'factory/<feature>' or 'main')")


class LaunchJobRequest(BaseModel):
    repo: str = Field(..., description="Target repository name in Test Organization (e.g. 'test3')")
    feature: str | None = Field(None, description="Feature / milestone slug (e.g. 'slug-generator')")
    issue: str | None = Field(None, description="Optional ticket ID (e.g. '01' or '42')")
    model: str = Field("deepseek-v4.1-flash", description="Model identifier")
    vm: bool = Field(False, description="Launch in VM Sandbox with Docker support")
    dev: bool = Field(False, description="Launch in dev preview mode with port 3000 keep-alive")


class CreateRepoRequest(BaseModel):
    name: str = Field(..., description="Project / repository name (e.g. 'inventory-tracker')")
    description: str | None = Field(None, description="Optional repository description")
    private: bool = Field(False, description="Whether created repository is private")


class StudioPromptRequest(BaseModel):
    repo: str = Field(..., description="Target repository name in Test Organization (e.g. 'inventory-tracker')")
    prompt: str = Field(..., description="User prompt describing what to build")
    model: str = Field("deepseek-v4.1-flash", description="Model identifier")
    vm: bool = Field(False, description="Launch in VM Sandbox with Docker support")
    milestone_title: str | None = Field(None, description="Optional custom milestone title")
    grill: bool = Field(True, description="Whether to conduct conversational grilling before building")
    history: list[dict[str, Any]] = Field(default_factory=list, description="Client chat history")


class ApprovePlanRequest(BaseModel):
    repo: str = Field(..., description="Target repository name in Test Organization (e.g. 'inventory-tracker')")
    prompt: str = Field(..., description="Prompt or approved plan summary")
    milestone_title: str | None = Field(None, description="Optional custom milestone title")
    draft_adr: dict[str, Any] | None = Field(None, description="Draft ADR details {filename, content, title}")
    context_update: str | None = Field(None, description="Optional updated CONTEXT.md content")
    model: str = Field("deepseek-v4.1-flash", description="Model identifier")
    vm: bool = Field(False, description="Launch in VM Sandbox with Docker support")


def create_app(
    registry: JobRegistry = job_registry,
    preview_reg: PreviewRegistry = preview_registry,
    db: StudioDatabase | None = None,
) -> FastAPI:
    """Creates and configures the FastAPI application."""
    if db is None:
        if getattr(registry, "db", None) is not None:
            db = registry.db
        elif registry is job_registry:
            db = StudioDatabase()
        else:
            db = StudioDatabase(":memory:")
    registry.db = db
    preview_reg.db = db
    registry.rehydrate()
    preview_reg.rehydrate()

    app = FastAPI(
        title="Factory Studio",
        description="Interactive testing interface for Software Factory on software-factory-09-test",
        version="1.0.0",
    )
    app.add_middleware(BasicAuthMiddleware)
    if getattr(registry, "preview_registry", None) is None:
        registry.preview_registry = preview_reg

    STATIC_DIST_DIR.mkdir(parents=True, exist_ok=True)
    assets_dir = STATIC_DIST_DIR / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
    app.mount("/static/dist", StaticFiles(directory=str(STATIC_DIST_DIR)), name="static_dist")

    def _get_spa_html() -> HTMLResponse:
        dist_index = STATIC_DIST_DIR / "index.html"
        if dist_index.is_file():
            return HTMLResponse(content=dist_index.read_text(encoding="utf-8"))
        return HTMLResponse(
            content="""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Factory Studio</title></head>
<body class="bg-slate-900 text-slate-100 p-8 font-sans">
  <div id="root">
    <h1 class="text-xl font-bold mb-2">Factory Studio &amp; Testing Console</h1>
    <p class="text-slate-400">Compiled SPA bundle not found in <code>factory/ui/static/dist/</code>. Run <code>pnpm --dir factory/ui/frontend build</code> to compile the frontend.</p>
  </div>
</body>
</html>""",
            status_code=200,
        )

    @app.get("/v2", response_class=RedirectResponse)
    async def v2_redirect_root(request: Request):
        query = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(url=f"/{query}", status_code=307)

    @app.get("/v2/{subpath:path}", response_class=RedirectResponse)
    async def v2_redirect_subpath(request: Request, subpath: str):
        query = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(url=f"/{subpath}{query}", status_code=307)

    @app.get("/", response_class=HTMLResponse)
    async def root_spa():
        return _get_spa_html()

    @app.exception_handler(404)
    @app.exception_handler(StarletteHTTPException)
    async def spa_404_fallback(request: Request, exc: Exception):
        status_code = getattr(exc, "status_code", 404)
        if status_code != 404:
            detail = getattr(exc, "detail", "Error")
            return JSONResponse(status_code=status_code, content={"detail": detail})
        path = request.url.path
        if path.startswith("/api") or path.startswith("/assets") or path.startswith("/static"):
            detail = getattr(exc, "detail", "Not Found")
            return JSONResponse(status_code=404, content={"detail": detail})
        if request.method == "GET":
            return _get_spa_html()
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

    @app.exception_handler(RepoCreationError)
    async def repo_creation_error_handler(request: Request, exc: RepoCreationError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.get("/api/repos")
    @app.get("/api/studio/repos")
    async def get_repos():
        detailed_repos = fetch_test_org_repos_detailed()
        return {
            "org": DEFAULT_TEST_ORG,
            "repos": detailed_repos,
        }

    @app.post("/api/repos", status_code=201)
    @app.post("/api/studio/repos", status_code=201)
    async def create_repo(req: CreateRepoRequest):
        repo_name = req.name.strip()
        valid, err_msg = validate_github_repo_name(repo_name)
        if not valid:
            raise HTTPException(status_code=400, detail=err_msg or "Invalid repository name.")

        result = instantiate_repo_from_template(
            repo_name=repo_name,
            description=req.description,
            private=req.private,
        )
        return JSONResponse(status_code=201, content=result)

    async def _ensure_sandbox_and_dispatch_job(
        repo: str,
        milestone_slug: str,
        issue_number: int | str,
        model: str,
        vm: bool,
        target_branch: str,
    ):
        active_sandbox, preview_url = preview_reg.get_active_sandbox(repo)
        preview_state = preview_reg.get_preview(repo)

        if active_sandbox is None:
            if not preview_state or preview_state.status in (PreviewStatus.STOPPED, PreviewStatus.FAILED, PreviewStatus.IDLE):
                preview_state = preview_reg.launch_preview(repo, branch=target_branch)

            active_sandbox, preview_url = await preview_reg.wait_for_serving(repo)
            preview_state = preview_reg.get_preview(repo)
            if active_sandbox is None and preview_state and preview_state.status == PreviewStatus.FAILED:
                raise HTTPException(
                    status_code=500,
                    detail=f"Unified Studio Sandbox failed to start: {preview_state.error_message or 'Unknown error'}",
                )

        if preview_state:
            preview_reg.update_branch(repo, target_branch)
            if not preview_url and preview_state.preview_url:
                preview_url = preview_state.preview_url

        effective_preview_url = preview_url or (preview_state.preview_url if preview_state else None)

        job = registry.create_job(
            repo=repo,
            feature=milestone_slug,
            issue=str(issue_number),
            model=model,
            vm=vm,
            dev=True,
        )
        job.preview_url = effective_preview_url
        registry.start_job(job.id)
        return job, preview_state, effective_preview_url

    @app.post("/api/studio/prompt")
    @app.post("/api/prompt")
    async def studio_prompt(req: StudioPromptRequest):
        repo = req.repo.strip() if req.repo else ""
        if not repo:
            raise HTTPException(status_code=400, detail="Repository name is required.")

        prompt = req.prompt.strip() if req.prompt else ""
        if not prompt:
            raise HTTPException(status_code=400, detail="Prompt is required.")

        # Persist User Prompt
        db.save_chat_message(
            repo=repo,
            role="user",
            content=prompt,
        )

        # 1. Fast Intent Classification Guard
        guard_result = evaluate_prompt_intent(prompt)
        if not guard_result.allowed:
            db.save_chat_message(
                repo=repo,
                role="assistant",
                content=guard_result.refusal_message or "Prompt rejected by intent guard.",
                turn_data={
                    "refusal": True,
                    "reason": guard_result.reason,
                    "category": guard_result.category,
                },
            )
            return {
                "accepted": False,
                "refusal": guard_result.refusal_message,
                "reason": guard_result.reason,
                "category": guard_result.category,
                "turn": None,
                "job": None,
                "issue": None,
                "milestone": None,
                "stage": None,
                "preview_url": None,
                "preview": None,
            }

        # 2. Conversational Grilling Assistant Turn (Grill Mode)
        if req.grill:
            assistant = GrillingAssistant()
            turn = await assistant.handle_turn(
                repo=repo,
                prompt=prompt,
                history=req.history,
                model=req.model,
            )
            turn_dict = turn.to_dict()
            db.save_chat_message(
                repo=repo,
                role="assistant",
                content=turn.summary or "Grilling turn response",
                turn_data=turn_dict,
            )
            return {
                "accepted": True,
                "refusal": None,
                "reason": None,
                "category": None,
                "turn": turn_dict,
                "job": None,
                "issue": None,
                "milestone": None,
                "stage": None,
                "preview_url": None,
                "preview": None,
            }

        # 3. Resolve or Create Active Milestone (Fast-Build Bypass)
        milestone = resolve_or_create_milestone(
            repo_name=repo,
            title=req.milestone_title,
        )
        milestone_slug = milestone["slug"]
        target_branch = f"factory/{milestone_slug}"

        # 4. Synthesize sequential GitHub Issue with acceptance criteria
        issue = synthesize_and_create_issue(
            repo_name=repo,
            prompt=prompt,
            milestone_number=milestone["number"],
            milestone_slug=milestone_slug,
        )

        # 5. Ensure Unified Studio Sandbox is active and dispatch Assembly Line job
        job, preview_state, effective_preview_url = await _ensure_sandbox_and_dispatch_job(
            repo=repo,
            milestone_slug=milestone_slug,
            issue_number=issue["number"],
            model=req.model,
            vm=req.vm,
            target_branch=target_branch,
        )

        db.save_chat_message(
            repo=repo,
            role="assistant",
            content=f"Dispatched assembly line job for {milestone_slug} (Issue #{issue['number']})",
            milestone_slug=milestone_slug,
            issue_number=issue["number"],
            turn_data={
                "job_id": job.id,
                "issue": issue,
                "milestone": milestone,
                "preview_url": effective_preview_url,
            },
        )

        # 6. Return job metadata, synthesized issue reference, stage tracking, preview state and tunnel URL
        return {
            "accepted": True,
            "refusal": None,
            "reason": None,
            "turn": None,
            "job": job.to_dict(),
            "issue": issue,
            "milestone": milestone,
            "stage": job.stage.value,
            "preview_url": effective_preview_url,
            "preview": preview_state.to_dict() if preview_state else None,
        }

    @app.post("/api/studio/approve")
    async def approve_plan_endpoint(req: ApprovePlanRequest):
        repo = req.repo.strip()
        if not repo:
            raise HTTPException(status_code=400, detail="Repository name is required.")
        prompt = req.prompt.strip()
        if not prompt:
            raise HTTPException(status_code=400, detail="Prompt is required.")

        # 1. Resolve or Create Active Milestone
        milestone = resolve_or_create_milestone(
            repo_name=repo,
            title=req.milestone_title,
        )
        milestone_slug = milestone["slug"]
        target_branch = f"factory/{milestone_slug}"

        # 2. Commit approved draft ADR and updated CONTEXT.md to branch factory/<milestone_slug>
        commit_approved_adr_to_branch(
            repo_name=repo,
            branch=target_branch,
            draft_adr=req.draft_adr,
            context_update=req.context_update,
        )

        # 3. Synthesize sequential GitHub Issue with acceptance criteria
        issue = synthesize_and_create_issue(
            repo_name=repo,
            prompt=prompt,
            milestone_number=milestone["number"],
            milestone_slug=milestone_slug,
        )

        # 4. Ensure Unified Studio Sandbox is active and dispatch Assembly Line job
        job, preview_state, effective_preview_url = await _ensure_sandbox_and_dispatch_job(
            repo=repo,
            milestone_slug=milestone_slug,
            issue_number=issue["number"],
            model=req.model,
            vm=req.vm,
            target_branch=target_branch,
        )

        # 5. Persist approved plan record to chat_messages
        db.save_chat_message(
            repo=repo,
            role="assistant",
            content=f"Plan approved for {milestone_slug} (Issue #{issue['number']}). Dispatched assembly line pipeline.",
            milestone_slug=milestone_slug,
            issue_number=issue["number"],
            turn_data={
                "status": "approved",
                "job_id": job.id,
                "branch": target_branch,
                "draft_adr": req.draft_adr,
                "issue": issue,
                "milestone": milestone,
            },
        )

        # 6. Return response
        return {
            "accepted": True,
            "job": job.to_dict(),
            "issue": issue,
            "milestone": milestone,
            "stage": job.stage.value,
            "preview_url": effective_preview_url,
            "preview": preview_state.to_dict() if preview_state else None,
            "branch": target_branch,
            "draft_adr": req.draft_adr,
        }

    @app.get("/api/studio/repos/{repo}/messages")
    async def get_studio_messages(repo: str):
        clean_repo = repo.strip()
        if not clean_repo:
            raise HTTPException(status_code=400, detail="Repository name is required.")
        messages = db.get_chat_messages(clean_repo)
        return {"repo": clean_repo, "messages": messages}

    @app.delete("/api/studio/repos/{repo}/messages")
    async def delete_studio_messages(repo: str):
        clean_repo = repo.strip()
        if not clean_repo:
            raise HTTPException(status_code=400, detail="Repository name is required.")
        deleted = db.delete_chat_messages(clean_repo)
        return {"repo": clean_repo, "deleted": deleted, "success": True}

    @app.post("/api/studio/repos/{repo}/preview", status_code=201)
    async def launch_preview_endpoint(repo: str, req: LaunchPreviewRequest | None = None):
        clean_repo = repo.strip()
        if not clean_repo:
            raise HTTPException(status_code=400, detail="Repository name is required.")
        branch = req.branch if req else None
        preview = preview_reg.launch_preview(clean_repo, branch=branch)
        return JSONResponse(status_code=201, content=preview.to_dict())

    @app.get("/api/studio/repos/{repo}/preview")
    async def get_preview_endpoint(repo: str):
        clean_repo = repo.strip()
        if not clean_repo:
            raise HTTPException(status_code=400, detail="Repository name is required.")
        preview = preview_reg.get_preview(clean_repo)
        if not preview:
            return PreviewState(repo=clean_repo).to_dict()
        return preview.to_dict()

    @app.delete("/api/studio/repos/{repo}/preview")
    async def stop_preview_endpoint(repo: str):
        clean_repo = repo.strip()
        if not clean_repo:
            raise HTTPException(status_code=400, detail="Repository name is required.")
        stopped = await preview_reg.stop_preview(clean_repo)
        if not stopped:
            raise HTTPException(
                status_code=400,
                detail=f"No active running preview found for repository '{clean_repo}'.",
            )
        return {"message": f"Preview for {clean_repo} stopped.", "success": True, "repo": clean_repo}

    @app.get("/api/studio/repos/{repo}/preview/stream")
    async def stream_preview_endpoint(repo: str, request: Request):
        clean_repo = repo.strip()
        if not clean_repo:
            raise HTTPException(status_code=400, detail="Repository name is required.")

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
                import queue as pyqueue
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



    @app.get("/api/repos/{repo}/scratch")
    async def get_repo_scratch(repo: str):
        metadata = fetch_repo_scratch_metadata(repo)
        return metadata

    @app.get("/api/repos/{repo}/milestones")
    async def get_repo_milestones(repo: str):
        metadata = fetch_repo_milestones_and_issues(repo)
        return metadata

    @app.get("/api/repos/{repo}/issues")
    async def get_repo_issues(repo: str, milestone: int | None = None, state: str = "all"):
        issues = fetch_repo_issues(repo, milestone_number=milestone, state=state)
        return {"repo": repo, "org": DEFAULT_TEST_ORG, "issues": issues}

    @app.get("/api/repos/{repo}/issues/{issue_number}")
    async def get_repo_issue_detail(repo: str, issue_number: int):
        issue = fetch_repo_issue(repo, issue_number=issue_number)
        if issue is None:
            raise HTTPException(status_code=404, detail=f"Issue #{issue_number} not found in {repo}.")
        return issue

    @app.post("/api/jobs")
    async def launch_job(req: LaunchJobRequest):
        if not req.repo or not req.repo.strip():
            raise HTTPException(status_code=400, detail="Repository name is required.")

        feature = (req.feature or "").strip()
        issue = (req.issue or "").strip() or None

        if not feature:
            if issue:
                feature = f"issue-{issue}"
            else:
                raise HTTPException(status_code=400, detail="Feature / milestone slug or issue ID is required.")

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

    @app.get("/api/jobs")
    async def list_jobs():
        return {"jobs": registry.list_jobs()}

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str):
        job = registry.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
        return job.to_dict()

    @app.post("/api/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str):
        success = registry.cancel_job(job_id)
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Job '{job_id}' is not currently running or not found.",
            )
        return {"message": f"Job {job_id} cancelled.", "success": True}

    @app.get("/api/jobs/{job_id}/stream")
    async def stream_job(job_id: str, request: Request):
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
                import queue as pyqueue
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

    return app
