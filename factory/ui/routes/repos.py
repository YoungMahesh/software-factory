"""Repository discovery, template instantiation, branch listing, and metadata routes."""

import sys
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import factory.ui.github as gh

router = APIRouter()


class CreateRepoRequest(BaseModel):
    name: str = Field(..., description="Project / repository name (e.g. 'inventory-tracker')")
    description: str | None = Field(None, description="Optional repository description")
    private: bool = Field(True, description="Whether created repository is private")


def _gh(attr: str):
    app = sys.modules.get("factory.ui.app")
    if app and hasattr(app, attr):
        return getattr(app, attr)
    return getattr(gh, attr)


@router.get("/api/repos")
@router.get("/api/studio/repos")
async def get_repos():
    detailed_repos = _gh("fetch_test_org_repos_detailed")()
    default_org = _gh("DEFAULT_TEST_ORG")
    return {
        "org": default_org,
        "repos": detailed_repos,
    }


@router.post("/api/repos", status_code=201)
@router.post("/api/studio/repos", status_code=201)
async def create_repo(req: CreateRepoRequest):
    repo_name = req.name.strip()
    valid, err_msg = _gh("validate_github_repo_name")(repo_name)
    if not valid:
        raise HTTPException(status_code=400, detail=err_msg or "Invalid repository name.")

    result = _gh("instantiate_repo_from_template")(
        repo_name=repo_name,
        description=req.description,
        private=req.private,
    )
    return JSONResponse(status_code=201, content=result)


@router.get("/api/studio/repos/{repo}/branches")
@router.get("/api/repos/{repo}/branches")
async def get_repo_branches_endpoint(repo: str):
    clean_repo = repo.strip()
    if not clean_repo:
        raise HTTPException(status_code=400, detail="Repository name is required.")
    branches, error_msg = _gh("fetch_repo_branches_with_diagnostics")(clean_repo)
    default_org = _gh("DEFAULT_TEST_ORG")
    resp: dict[str, Any] = {
        "repo": clean_repo,
        "org": default_org,
        "branches": branches,
        "default_branch": "main",
    }
    if error_msg:
        resp["error"] = error_msg
    return resp



@router.get("/api/repos/{repo}/milestones")
async def get_repo_milestones(repo: str):
    metadata = _gh("fetch_repo_milestones_and_issues")(repo)
    return metadata


@router.get("/api/repos/{repo}/issues")
async def get_repo_issues(repo: str, milestone: int | None = None, state: str = "all"):
    issues = _gh("fetch_repo_issues")(repo, milestone_number=milestone, state=state)
    default_org = _gh("DEFAULT_TEST_ORG")
    return {"repo": repo, "org": default_org, "issues": issues}


@router.get("/api/repos/{repo}/issues/{issue_number}")
async def get_repo_issue_detail(repo: str, issue_number: int):
    issue = _gh("fetch_repo_issue")(repo, issue_number=issue_number)
    if issue is None:
        raise HTTPException(status_code=404, detail=f"Issue #{issue_number} not found in {repo}.")
    return issue
