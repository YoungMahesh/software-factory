"""FastAPI Web Application for Factory Testing Console.

Serves the interactive testing dashboard, REST endpoints for repo and
issue discovery, and Server-Sent Events (SSE) for live terminal streaming.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from factory.ui.auth import BasicAuthMiddleware
from factory.ui.github import (
    DEFAULT_TEST_ORG,
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
from factory.ui.guard import evaluate_prompt_intent
from factory.ui.registry import JobRegistry, job_registry

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


class LaunchJobRequest(BaseModel):
    repo: str = Field(..., description="Target repository name in Test Organization (e.g. 'test3')")
    feature: str | None = Field(None, description="Feature / milestone slug (e.g. 'slug-generator')")
    issue: str | None = Field(None, description="Optional ticket ID (e.g. '01' or '42')")
    model: str = Field("deepseek-v4.1-flash", description="Model identifier")
    vm: bool = Field(False, description="Launch in VM Sandbox with Docker support")


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


def create_app(registry: JobRegistry = job_registry) -> FastAPI:
    """Creates and configures the FastAPI application."""
    app = FastAPI(
        title="Factory Studio",
        description="Interactive testing interface for Software Factory on software-factory-09-test",
        version="1.0.0",
    )
    app.add_middleware(BasicAuthMiddleware)

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        repos = fetch_test_org_repos()
        jobs = registry.list_jobs()
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "org": DEFAULT_TEST_ORG,
                "repos": repos,
                "jobs": jobs,
            },
        )

    @app.get("/api/repos")
    async def get_repos():
        detailed_repos = fetch_test_org_repos_detailed()
        return {
            "org": DEFAULT_TEST_ORG,
            "repos": detailed_repos,
        }

    @app.get("/api/studio/repos")
    async def get_studio_repos():
        detailed_repos = fetch_test_org_repos_detailed()
        return {
            "org": DEFAULT_TEST_ORG,
            "repos": detailed_repos,
        }

    @app.post("/api/repos", status_code=201)
    async def create_repo(req: CreateRepoRequest):
        repo_name = req.name.strip()
        valid, err_msg = validate_github_repo_name(repo_name)
        if not valid:
            raise HTTPException(status_code=400, detail=err_msg or "Invalid repository name.")

        try:
            result = instantiate_repo_from_template(
                repo_name=repo_name,
                description=req.description,
                private=req.private,
            )
            return JSONResponse(status_code=201, content=result)
        except RepoCreationError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

    @app.post("/api/studio/repos", status_code=201)
    async def create_studio_repo(req: CreateRepoRequest):
        return await create_repo(req)

    @app.post("/api/studio/prompt")
    @app.post("/api/prompt")
    async def studio_prompt(req: StudioPromptRequest):
        repo = req.repo.strip() if req.repo else ""
        if not repo:
            raise HTTPException(status_code=400, detail="Repository name is required.")

        prompt = req.prompt.strip() if req.prompt else ""
        if not prompt:
            raise HTTPException(status_code=400, detail="Prompt is required.")

        # 1. Fast Intent Classification Guard
        guard_result = evaluate_prompt_intent(prompt)
        if not guard_result.allowed:
            return {
                "accepted": False,
                "refusal": guard_result.refusal_message,
                "reason": guard_result.reason,
                "category": guard_result.category,
                "job": None,
                "issue": None,
                "milestone": None,
                "stage": None,
            }

        # 2. Resolve or Create Active Milestone
        milestone = resolve_or_create_milestone(
            repo_name=repo,
            title=req.milestone_title,
        )

        # 3. Synthesize sequential GitHub Issue with acceptance criteria
        issue = synthesize_and_create_issue(
            repo_name=repo,
            prompt=prompt,
            milestone_number=milestone["number"],
            milestone_slug=milestone["slug"],
        )

        # 4. Dispatch autonomous assembly line job targeting the issue on branch factory/<milestone>
        job = registry.create_job(
            repo=repo,
            feature=milestone["slug"],
            issue=str(issue["number"]),
            model=req.model,
            vm=req.vm,
        )
        registry.start_job(job.id)

        # 5. Return job metadata, synthesized issue reference, and stage tracking
        return {
            "accepted": True,
            "refusal": None,
            "reason": None,
            "job": job.to_dict(),
            "issue": issue,
            "milestone": milestone,
            "stage": job.stage.value,
        }



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
