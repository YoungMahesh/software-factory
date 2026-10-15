"""Grilling turn interactions, chat history retrieval, prompt intent evaluation, and plan approval."""

import sys
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from factory.ui.db import StudioDatabase
from factory.ui.grill import GrillingAssistant
from factory.ui.guard import evaluate_prompt_intent
import factory.ui.github as gh
from factory.ui.registry import (
    JobRegistry,
    job_registry,
    PreviewRegistry,
    preview_registry,
    PreviewStatus,
)

router = APIRouter()


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


def _get_registry(request: Request) -> JobRegistry:
    return getattr(request.app.state, "registry", job_registry)


def _get_preview_reg(request: Request) -> PreviewRegistry:
    return getattr(request.app.state, "preview_reg", preview_registry)


def _get_db(request: Request) -> StudioDatabase:
    db = getattr(request.app.state, "db", None)
    if db is not None:
        return db
    reg = _get_registry(request)
    if getattr(reg, "db", None) is not None:
        return reg.db
    return StudioDatabase()


def _gh(attr: str):
    app = sys.modules.get("factory.ui.app")
    if app and hasattr(app, attr):
        return getattr(app, attr)
    return getattr(gh, attr)


async def _ensure_sandbox_and_dispatch_job(
    repo: str,
    feature: str,
    issue_number: int | str | None,
    model: str,
    vm: bool,
    target_branch: str,
    registry: JobRegistry,
    preview_reg: PreviewRegistry,
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


@router.post("/api/studio/prompt")
@router.post("/api/prompt")
async def studio_prompt(req: StudioPromptRequest, request: Request):
    repo = req.repo.strip() if req.repo else ""
    if not repo:
        raise HTTPException(status_code=400, detail="Repository name is required.")

    prompt = req.prompt.strip() if req.prompt else ""
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required.")

    db = _get_db(request)
    registry = _get_registry(request)
    preview_reg = _get_preview_reg(request)

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
        milestone_slug = _gh("normalize_milestone_slug")(req.milestone_title) if req.milestone_title else None
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
    milestone = _gh("resolve_or_create_milestone")(
        repo_name=repo,
        title=req.milestone_title,
    )
    milestone_slug = milestone["slug"]
    target_branch = f"factory/{milestone_slug}"

    # 4. Synthesize sequential GitHub Issue with acceptance criteria
    issue = _gh("synthesize_and_create_issue")(
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
        registry=registry,
        preview_reg=preview_reg,
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


@router.post("/api/studio/approve")
async def approve_plan_endpoint(req: ApprovePlanRequest, request: Request):
    repo = req.repo.strip()
    if not repo:
        raise HTTPException(status_code=400, detail="Repository name is required.")
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required.")

    db = _get_db(request)
    registry = _get_registry(request)
    preview_reg = _get_preview_reg(request)

    # 1. Resolve or Create Active Milestone
    milestone = _gh("resolve_or_create_milestone")(
        repo_name=repo,
        title=req.milestone_title,
    )
    milestone_slug = milestone["slug"]
    target_branch = f"factory/{milestone_slug}"

    # 2. Commit approved draft ADR and updated CONTEXT.md to branch factory/<milestone_slug>
    _gh("commit_approved_adr_to_branch")(
        repo_name=repo,
        branch=target_branch,
        draft_adr=req.draft_adr,
        context_update=req.context_update,
    )

    # 3. Synthesize sequential GitHub Issue with acceptance criteria
    issue = _gh("synthesize_and_create_issue")(
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
        registry=registry,
        preview_reg=preview_reg,
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


@router.post("/api/studio/dispatch")
async def studio_dispatch_endpoint(req: StudioDispatchRequest, request: Request):
    repo = req.repo.strip() if req.repo else ""
    if not repo:
        raise HTTPException(status_code=400, detail="Repository name is required.")

    db = _get_db(request)
    registry = _get_registry(request)
    preview_reg = _get_preview_reg(request)

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
            fetched_issue = _gh("fetch_repo_issue")(repo, issue_int)
            if fetched_issue and fetched_issue.get("milestone"):
                m_data = fetched_issue["milestone"]
                milestone_str = m_data.get("slug") or m_data.get("title")
        except Exception:
            pass

    if milestone_str:
        milestone_slug = _gh("normalize_milestone_slug")(milestone_str)
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
        registry=registry,
        preview_reg=preview_reg,
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


@router.get("/api/studio/repos/{repo}/messages")
async def get_studio_messages(repo: str, request: Request):
    clean_repo = repo.strip()
    if not clean_repo:
        raise HTTPException(status_code=400, detail="Repository name is required.")
    db = _get_db(request)
    messages = db.get_chat_messages(clean_repo)
    return {"repo": clean_repo, "messages": messages}


@router.delete("/api/studio/repos/{repo}/messages")
async def delete_studio_messages(repo: str, request: Request):
    clean_repo = repo.strip()
    if not clean_repo:
        raise HTTPException(status_code=400, detail="Repository name is required.")
    db = _get_db(request)
    deleted = db.delete_chat_messages(clean_repo)
    return {"repo": clean_repo, "deleted": deleted, "success": True}
