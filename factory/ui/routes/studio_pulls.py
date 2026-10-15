"""Pull request discovery, delivery gate evaluation, and merge controls."""

import sys

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from factory.ui.db import StudioDatabase
import factory.ui.github as gh
from factory.ui.registry import (
    JobRegistry,
    job_registry,
    PreviewRegistry,
    preview_registry,
)

router = APIRouter()


class MergePullRequestRequest(BaseModel):
    commit_title: str | None = Field(None, description="Optional custom squash commit title")
    commit_message: str | None = Field(None, description="Optional custom squash commit message")


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


@router.get("/api/studio/repos/{repo}/pulls")
async def get_studio_pull_requests(
    repo: str,
    branch: str | None = None,
    state: str = "all",
):
    clean_repo = repo.strip() if repo else ""
    if not clean_repo:
        raise HTTPException(status_code=400, detail="Repository name is required.")
    pulls = _gh("fetch_repo_pull_requests")(clean_repo, branch=branch, state=state)
    return {
        "repo": clean_repo,
        "pulls": pulls,
    }


@router.post("/api/studio/repos/{repo}/pulls/{pull_number}/merge")
async def merge_studio_pull_request(
    repo: str,
    pull_number: int,
    request: Request,
    req: MergePullRequestRequest | None = None,
):
    clean_repo = repo.strip() if repo else ""
    if not clean_repo:
        raise HTTPException(status_code=400, detail="Repository name is required.")

    registry = _get_registry(request)
    preview_reg = _get_preview_reg(request)
    db = _get_db(request)

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

    pull_error_cls = _gh("PullRequestMergeError")
    try:
        merge_res = _gh("merge_repo_pull_request")(
            repo_name=clean_repo,
            pull_number=pull_number,
            commit_title=commit_title,
            commit_message=commit_message,
        )
    except pull_error_cls as e:
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
