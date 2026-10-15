"""FastAPI Web Application for Factory Testing Console.

Serves the interactive testing dashboard, REST endpoints for repo and
issue discovery, and Server-Sent Events (SSE) for live terminal streaming.
"""

import asyncio
import json
from pathlib import Path
import re
import shlex
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
    fetch_repo_branches,
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
    normalize_milestone_slug,
    fetch_repo_pull_requests,
    merge_repo_pull_request,
    PullRequestMergeError,
    fetch_repo_branches,
    fetch_repo_branches_with_diagnostics,
    reopen_repo_issue_for_rollback,
)
from factory.ui.tracker import update_local_markdown_issue_for_rollback
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


class PreviewSyncRequest(BaseModel):
    branch: str | None = Field(None, description="Optional target branch to synchronize (defaults to active preview branch or main)")


class PreviewBranchRequest(BaseModel):
    branch: str = Field(..., description="Target branch to switch to")


class RollbackTurnRequest(BaseModel):
    message_id: str | None = Field(None, description="Optional target assistant message ID to roll back")
    branch: str | None = Field(None, description="Optional target branch to roll back (defaults to active preview branch)")


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
    private: bool = Field(True, description="Whether created repository is private")


class StudioPromptRequest(BaseModel):
    repo: str = Field(..., description="Target repository name in Test Organization (e.g. 'inventory-tracker')")
    prompt: str = Field(..., description="User prompt describing what to build")
    model: str = Field("deepseek-v4.1-flash", description="Model identifier")
    vm: bool = Field(False, description="Launch in VM Sandbox with Docker support")
    milestone_title: str | None = Field(None, description="Optional custom milestone title")
    grill: bool = Field(True, description="Whether to conduct conversational grilling before building")
    history: list[dict[str, Any]] = Field(default_factory=list, description="Client chat history")
    mock: bool = Field(False, description="Explicit mock mode for testing")


class ApprovePlanRequest(BaseModel):
    repo: str = Field(..., description="Target repository name in Test Organization (e.g. 'inventory-tracker')")
    prompt: str = Field(..., description="Prompt or approved plan summary")
    milestone_title: str | None = Field(None, description="Optional custom milestone title")
    draft_adr: dict[str, Any] | None = Field(None, description="Draft ADR details {filename, content, title}")
    context_update: str | None = Field(None, description="Optional updated CONTEXT.md content")
    model: str = Field("deepseek-v4.1-flash", description="Model identifier")
    vm: bool = Field(False, description="Launch in VM Sandbox with Docker support")


class StudioDispatchRequest(BaseModel):
    repo: str = Field(..., description="Target repository name in Test Organization (e.g. 'inventory-tracker')")
    issue: int | str | None = Field(None, description="Optional ticket number or ID (e.g. 42 or '42')")
    issue_number: int | None = Field(None, description="Optional ticket number")
    milestone: str | None = Field(None, description="Optional milestone slug or title")
    milestone_slug: str | None = Field(None, description="Optional milestone slug")
    milestone_title: str | None = Field(None, description="Optional milestone title")
    model: str = Field("deepseek-v4.1-flash", description="Model identifier")
    vm: bool = Field(False, description="Launch in VM Sandbox with Docker support")


class MergePullRequestRequest(BaseModel):
    commit_title: str | None = Field(None, description="Optional custom squash commit title")
    commit_message: str | None = Field(None, description="Optional custom squash commit message")


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
    assert db is not None
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
        feature: str,
        issue_number: int | str | None,
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

        issue_param = str(issue_number) if issue_number is not None else None
        job = registry.create_job(
            repo=repo,
            feature=feature,
            issue=issue_param,
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
            assistant = GrillingAssistant(mock=req.mock)
            milestone_slug = normalize_milestone_slug(req.milestone_title) if req.milestone_title else None
            turn = await assistant.handle_turn(
                repo=repo,
                prompt=prompt,
                history=req.history,
                model=req.model,
                milestone_slug=milestone_slug,
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
            feature=milestone_slug,
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
            feature=milestone_slug,
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

    @app.post("/api/studio/dispatch")
    async def studio_dispatch_endpoint(req: StudioDispatchRequest):
        repo = req.repo.strip() if req.repo else ""
        if not repo:
            raise HTTPException(status_code=400, detail="Repository name is required.")

        # Resolve issue identifier
        issue_val = None
        if req.issue_number is not None:
            issue_val = req.issue_number
        elif req.issue is not None:
            try:
                issue_val = int(str(req.issue).strip())
            except (ValueError, TypeError):
                issue_val = str(req.issue).strip() or None

        # Resolve milestone identifier
        milestone_raw = req.milestone_slug or req.milestone or req.milestone_title
        milestone_str = milestone_raw.strip() if milestone_raw and isinstance(milestone_raw, str) else None

        if issue_val is None and not milestone_str:
            raise HTTPException(
                status_code=400,
                detail="Either milestone or issue number must be provided for dispatch.",
            )

        # If issue is specified without an explicit milestone, attempt lookup via GitHub
        if issue_val is not None and not milestone_str:
            try:
                issue_int = int(issue_val)
                fetched_issue = fetch_repo_issue(repo, issue_int)
                if fetched_issue and fetched_issue.get("milestone"):
                    m_data = fetched_issue["milestone"]
                    milestone_str = m_data.get("slug") or m_data.get("title")
            except Exception:
                pass

        if milestone_str:
            milestone_slug = normalize_milestone_slug(milestone_str)
            target_branch = f"factory/{milestone_slug}"
            feature_name = milestone_slug
        else:
            milestone_slug = None
            target_branch = f"factory/issue-{issue_val}"
            feature_name = f"issue-{issue_val}"

        job, preview_state, effective_preview_url = await _ensure_sandbox_and_dispatch_job(
            repo=repo,
            feature=feature_name,
            issue_number=issue_val,
            model=req.model,
            vm=req.vm,
            target_branch=target_branch,
        )

        # Structured execution card persisted to SQLite chat_messages
        if issue_val is not None and milestone_slug:
            card_content = f"Dispatched issue #{issue_val} for milestone '{milestone_slug}' on branch '{target_branch}'."
        elif issue_val is not None:
            card_content = f"Dispatched standalone issue #{issue_val} on branch '{target_branch}'."
        else:
            card_content = f"Dispatched milestone batch for '{milestone_slug}' on branch '{target_branch}'."

        turn_data = {
            "type": "dispatch_card",
            "job_id": job.id,
            "issue_number": issue_val,
            "milestone_slug": milestone_slug,
            "target_branch": target_branch,
            "preview_url": effective_preview_url,
        }

        db.save_chat_message(
            repo=repo,
            role="assistant",
            content=card_content,
            milestone_slug=milestone_slug,
            issue_number=issue_val if isinstance(issue_val, int) else None,
            turn_data=turn_data,
        )

        return {
            "accepted": True,
            "job": job.to_dict(),
            "issue_number": issue_val,
            "milestone_slug": milestone_slug,
            "branch": target_branch,
            "target_branch": target_branch,
            "preview_url": effective_preview_url,
            "preview": preview_state.to_dict() if preview_state else None,
            "stage": job.stage.value,
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

    @app.get("/api/studio/repos/{repo}/pulls")
    async def get_studio_pull_requests(
        repo: str,
        branch: str | None = None,
        state: str = "all",
    ):
        clean_repo = repo.strip() if repo else ""
        if not clean_repo:
            raise HTTPException(status_code=400, detail="Repository name is required.")
        pulls = fetch_repo_pull_requests(clean_repo, branch=branch, state=state)
        return {
            "repo": clean_repo,
            "pulls": pulls,
        }

    @app.post("/api/studio/repos/{repo}/pulls/{pull_number}/merge")
    async def merge_studio_pull_request(
        repo: str,
        pull_number: int,
        req: MergePullRequestRequest | None = None,
    ):
        clean_repo = repo.strip() if repo else ""
        if not clean_repo:
            raise HTTPException(status_code=400, detail="Repository name is required.")

        # Merging is strictly disabled while the Assembly Line is actively executing or queued
        active_jobs = [
            j for j in registry.list_jobs()
            if j.get("repo") == clean_repo and j.get("status") in ("RUNNING", "QUEUED")
        ]
        if active_jobs:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot merge pull request #{pull_number} while an assembly line job is active or queued for repository '{clean_repo}'.",
            )

        commit_title = req.commit_title if req else None
        commit_message = req.commit_message if req else None

        try:
            merge_res = merge_repo_pull_request(
                repo_name=clean_repo,
                pull_number=pull_number,
                commit_title=commit_title,
                commit_message=commit_message,
            )
        except PullRequestMergeError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to merge pull request #{pull_number}: {e}")

        # Post-merge live preview sandbox synchronization
        preview_synced = preview_reg.sync_sandbox_to_main(clean_repo)

        # Record a structured Delivery Gate Card in SQLite chat_messages table
        card_content = f"Merged Feature Pull Request #{pull_number} into main. Live preview synchronized."
        turn_data = {
            "type": "delivery_gate",
            "status": "merged",
            "merged": True,
            "pull_number": pull_number,
            "sha": merge_res.get("sha"),
            "branch": merge_res.get("branch"),
            "commit_title": merge_res.get("commit_title"),
            "commit_message": merge_res.get("commit_message"),
            "preview_synced": preview_synced,
            "result": merge_res,
        }

        db.save_chat_message(
            repo=clean_repo,
            role="assistant",
            content=card_content,
            turn_data=turn_data,
        )

        return {
            "accepted": True,
            "merged": True,
            "result": merge_res,
            "preview_synced": preview_synced,
        }

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

    def _execute_in_sandbox_sync(
        active_sandbox: Any,
        clean_repo: str,
        bare_repo: str,
        target_branch: str,
        action_desc: str,
    ) -> str | None:
        """Executes in-container branch checkout, remote fetch, and diff-aware package install."""
        import concurrent.futures
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

    def _execute_in_sandbox_rollback(
        active_sandbox: Any,
        clean_repo: str,
        bare_repo: str,
        target_branch: str,
        commit_sha: str | None,
    ) -> tuple[str, str]:
        """Executes in-container git revert --no-edit, pushes to remote, and runs diff-aware pnpm install."""
        import concurrent.futures

        target_commit_expr = shlex.quote(commit_sha) if commit_sha else "$OLD_SHA"
        revert_script = (
            f"cd /root/{bare_repo} && "
            f"git fetch origin {shlex.quote(target_branch)} && "
            f"(git checkout {shlex.quote(target_branch)} 2>/dev/null || git checkout -B {shlex.quote(target_branch)} origin/{shlex.quote(target_branch)}) && "
            f"git reset --hard origin/{shlex.quote(target_branch)} && "
            "git clean -fd && "
            'OLD_SHA=$(git rev-parse HEAD 2>/dev/null || echo "") && '
            f'TARGET_COMMIT={target_commit_expr} && '
            'echo "ORIGINAL_COMMIT_SHA:$(git rev-parse --short $TARGET_COMMIT)" && '
            'if ! git revert --no-edit "$TARGET_COMMIT"; then '
            'echo "Revert conflict encountered. Aborting..." >&2; '
            'git revert --abort; '
            'exit 1; '
            'fi && '
            f"git push origin {shlex.quote(target_branch)} && "
            'NEW_SHA=$(git rev-parse HEAD) && '
            'echo "REVERT_COMMIT_SHA:$(git rev-parse --short HEAD)" && '
            'if [ -n "$OLD_SHA" ] && git diff --name-only "$OLD_SHA" "$NEW_SHA" | grep -E \'^(package\\.json|pnpm-lock\\.yaml)$\' >/dev/null; then '
            'pnpm install --prefer-offline; '
            'fi'
        )

        preview_reg.append_log(
            clean_repo,
            f"↩️ [ROLLBACK] Reverting commit {commit_sha or 'HEAD'} on origin/{target_branch}...\n",
            flush=True,
        )

        proc = active_sandbox.exec("bash", "-c", revert_script)
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
                        if subline.startswith("ORIGINAL_COMMIT_SHA:") or subline.startswith("REVERT_COMMIT_SHA:"):
                            continue
                        prefix = "❌ [ROLLBACK ERROR] " if is_err else "↩️ [ROLLBACK] "
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
            preview_reg.append_log(clean_repo, f"❌ [ROLLBACK ERROR] {err_msg}\n", flush=True)
            raise HTTPException(
                status_code=400,
                detail=f"Turn rollback failed: {err_msg}",
            )

        full_output = "".join(stdout_lines)
        orig_sha_match = re.search(r"ORIGINAL_COMMIT_SHA:([^\r\n]+)", full_output)
        raw_orig_sha = orig_sha_match.group(1).strip() if orig_sha_match else (commit_sha or "HEAD")
        original_sha = raw_orig_sha[:7] if len(raw_orig_sha) >= 7 and raw_orig_sha != "HEAD" else raw_orig_sha

        rev_sha_match = re.search(r"REVERT_COMMIT_SHA:([^\r\n]+)", full_output)
        raw_rev_sha = rev_sha_match.group(1).strip() if rev_sha_match else "unknown"
        revert_sha = raw_rev_sha[:7] if len(raw_rev_sha) >= 7 and raw_rev_sha != "unknown" else raw_rev_sha

        preview_reg.append_log(
            clean_repo,
            f"↩️ [ROLLBACK] Successfully reverted {original_sha} (revert commit {revert_sha}) on {target_branch}.\n",
            flush=True,
        )
        return original_sha, revert_sha

    @app.post("/api/studio/repos/{repo}/turns/rollback")
    async def rollback_turn_endpoint(repo: str, req: RollbackTurnRequest | None = None):
        clean_repo = repo.strip()
        if not clean_repo:
            raise HTTPException(status_code=400, detail="Repository name is required.")

        # 1. Concurrency safety guard: strictly reject if an assembly line job is active
        if registry.is_job_active(clean_repo):
            raise HTTPException(
                status_code=409,
                detail=f"Cannot rollback turn while an Assembly Line Pipeline job is active or queued for repository '{clean_repo}'.",
            )

        # 2. Determine target branch
        preview = preview_reg.get_preview(clean_repo)
        explicit_branch = req.branch.strip() if req and req.branch and req.branch.strip() else None

        # 3. Resolve target message and turn data from SQLite chat history
        messages = db.get_chat_messages(clean_repo)
        target_msg: dict[str, Any] | None = None

        if req and req.message_id:
            for m in messages:
                if m.get("id") == req.message_id:
                    target_msg = m
                    break
            if not target_msg:
                raise HTTPException(
                    status_code=400,
                    detail=f"Turn message '{req.message_id}' not found for repository '{clean_repo}'.",
                )
            if target_msg.get("turn_data", {}).get("reverted"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Turn message '{req.message_id}' has already been reverted.",
                )
            target_branch = (
                explicit_branch
                or target_msg.get("turn_data", {}).get("branch")
                or (preview.branch if preview and preview.branch else "main")
            )
        else:
            target_branch = explicit_branch or (preview.branch if preview and preview.branch else "main")
            # Find latest completed code-producing turn on active branch in reverse order
            for m in reversed(messages):
                t_data = m.get("turn_data")
                if not isinstance(t_data, dict):
                    continue
                if t_data.get("reverted"):
                    continue
                if t_data.get("refusal") or t_data.get("type") == "turn_rollback":
                    continue
                is_code_producing = (
                    m.get("role") == "assistant"
                    and (
                        t_data.get("commit_sha")
                        or t_data.get("sha")
                        or t_data.get("job_id")
                        or t_data.get("issue")
                        or t_data.get("issue_number")
                        or m.get("issue_number") is not None
                    )
                )
                if not is_code_producing:
                    continue
                msg_branch = t_data.get("branch")
                if msg_branch and msg_branch != target_branch:
                    continue
                target_msg = m
                break

        # Merge safety guard: strictly reject if target branch is 'main' or PR has already been merged into main
        if not target_branch or target_branch == "main":
            raise HTTPException(
                status_code=400,
                detail="Cannot roll back turn: target branch is 'main' or has already been merged into main.",
            )

        prs = fetch_repo_pull_requests(clean_repo, branch=target_branch, state="all")
        for pr in prs:
            if pr.get("merged") or pr.get("status") == "merged":
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot roll back turn: Feature Pull Request #{pr.get('number')} for branch '{target_branch}' has already been merged into main.",
                )

        if not target_msg:
            raise HTTPException(
                status_code=400,
                detail=f"No completed code-producing turn found to roll back on branch '{target_branch}'.",
            )

        # 4. Auto-boot fallback: ensure Unified Studio Sandbox is running
        active_sandbox, _ = preview_reg.get_active_sandbox(clean_repo)
        preview_state = preview_reg.get_preview(clean_repo)

        if active_sandbox is None or preview_state is None or preview_state.status != PreviewStatus.SERVING:
            if not preview_state or preview_state.status in (PreviewStatus.STOPPED, PreviewStatus.FAILED, PreviewStatus.IDLE):
                preview_state = preview_reg.launch_preview(clean_repo, branch=target_branch)

            active_sandbox, _ = await preview_reg.wait_for_serving(clean_repo)
            preview_state = preview_reg.get_preview(clean_repo)
            if active_sandbox is None and preview_state and preview_state.status == PreviewStatus.FAILED:
                raise HTTPException(
                    status_code=500,
                    detail=f"Unified Studio Sandbox failed to start: {preview_state.error_message or 'Unknown error'}",
                )

        if active_sandbox is None:
            raise HTTPException(
                status_code=500,
                detail="Unified Studio Sandbox is not available to execute turn rollback.",
            )

        bare_repo = clean_repo.split("/")[-1]
        target_commit = (
            (target_msg.get("turn_data", {}).get("commit_sha") or target_msg.get("turn_data", {}).get("sha"))
            if target_msg is not None
            else None
        )

        original_sha, revert_sha = _execute_in_sandbox_rollback(
            active_sandbox=active_sandbox,
            clean_repo=clean_repo,
            bare_repo=bare_repo,
            target_branch=target_branch,
            commit_sha=target_commit,
        )

        # 5. Broadcast SSE preview_refresh
        preview_reg.broadcast_refresh(clean_repo)

        # 6. Coordinate issue tracker
        issue_num = None
        if target_msg is not None:
            issue_num = target_msg.get("issue_number")
            if issue_num is None:
                t_issue = target_msg.get("turn_data", {}).get("issue_number") or target_msg.get("turn_data", {}).get("issue")
                if isinstance(t_issue, dict):
                    issue_num = t_issue.get("number")
                elif t_issue is not None:
                    issue_num = t_issue

        if issue_num is not None:
            try:
                parsed_issue_num = int(issue_num)
                reopen_repo_issue_for_rollback(
                    repo_name=clean_repo,
                    issue_number=parsed_issue_num,
                    original_commit_sha=original_sha,
                    revert_commit_sha=revert_sha,
                )
            except Exception as e:
                preview_reg.append_log(clean_repo, f"⚠️ [ROLLBACK] Issue tracker reopen notice: {e}\n", flush=True)

        update_local_markdown_issue_for_rollback(
            repo_name=clean_repo,
            feature=target_branch.removeprefix("factory/") if target_branch.startswith("factory/") else None,
            issue_number=issue_num,
        )

        # 7. SQLite database persistence
        if target_msg is not None:
            db.mark_chat_message_reverted(
                message_id=target_msg["id"],
                revert_commit=revert_sha,
            )
        db.save_rollback_message(
            repo=clean_repo,
            original_message_id=target_msg["id"] if target_msg is not None else None,
            original_commit_sha=original_sha,
            revert_commit_sha=revert_sha,
            issue_number=issue_num,
            branch=target_branch,
        )

        issue_display = f" for Issue #{issue_num}" if issue_num else ""
        return {
            "success": True,
            "branch": target_branch,
            "original_commit": original_sha,
            "revert_commit": revert_sha,
            "issue_number": issue_num,
            "message": f"Rolled back turn{issue_display} (commit {original_sha} ➔ {revert_sha}).",
        }

    @app.post("/api/studio/repos/{repo}/preview/sync")
    async def sync_preview_endpoint(repo: str, req: PreviewSyncRequest | None = None):
        clean_repo = repo.strip()
        bare_repo = clean_repo.split("/")[-1]

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

    @app.post("/api/studio/repos/{repo}/preview/branch")
    @app.post("/api/repos/{repo}/preview/branch")
    async def switch_preview_branch_endpoint(repo: str, req: PreviewBranchRequest):
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

    @app.get("/api/studio/repos/{repo}/branches")
    @app.get("/api/repos/{repo}/branches")
    async def get_repo_branches_endpoint(repo: str):
        clean_repo = repo.strip()
        if not clean_repo:
            raise HTTPException(status_code=400, detail="Repository name is required.")
        branches, error_msg = fetch_repo_branches_with_diagnostics(clean_repo)
        resp: dict[str, Any] = {
            "repo": clean_repo,
            "org": DEFAULT_TEST_ORG,
            "branches": branches,
            "default_branch": "main",
        }
        if error_msg:
            resp["error"] = error_msg
        return resp
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
