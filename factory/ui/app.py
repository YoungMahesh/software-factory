"""FastAPI Web Application for Factory Testing Console.

Serves the interactive testing dashboard, REST endpoints for repo and
issue discovery, and Server-Sent Events (SSE) for live terminal streaming.
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from factory.ui.auth import BasicAuthMiddleware
from factory.ui.db import StudioDatabase
from factory.ui.github import (
    DEFAULT_TEST_ORG,
    PullRequestMergeError,
    RepoCreationError,
    commit_approved_adr_to_branch,
    fetch_repo_branches,
    fetch_repo_branches_with_diagnostics,
    fetch_repo_issue,
    fetch_repo_issues,
    fetch_repo_milestones_and_issues,
    fetch_repo_pull_requests,
    fetch_test_org_repos,
    fetch_test_org_repos_detailed,
    instantiate_repo_from_template,
    merge_repo_pull_request,
    normalize_milestone_slug,
    reopen_repo_issue_for_rollback,
    resolve_or_create_milestone,
    synthesize_and_create_issue,
    validate_github_repo_name,
)
from factory.ui.registry import (
    JobRegistry,
    job_registry,
    PreviewRegistry,
    preview_registry,
    PreviewState,
    PreviewStatus,
)
from factory.ui.routes.chat import (
    ApprovePlanRequest,
    StudioDispatchRequest,
    StudioPromptRequest,
    router as chat_router,
)
from factory.ui.routes.files import router as files_router
from factory.ui.routes.jobs import LaunchJobRequest, router as jobs_router
from factory.ui.routes.preview import (
    LaunchPreviewRequest,
    PreviewBranchRequest,
    PreviewSyncRequest,
    UpdatePreviewBranchRequest,
    router as preview_router,
)
from factory.ui.routes.pulls import (
    MergePullRequestRequest,
    router as pulls_router,
)
from factory.ui.routes.repos import CreateRepoRequest, router as repos_router
from factory.ui.routes.rollback import (
    RollbackTurnRequest,
    router as rollback_router,
)
from factory.ui.tracker import update_local_markdown_issue_for_rollback

STATIC_DIST_DIR = Path(__file__).resolve().parent / "static" / "dist"


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
            try:
                db = StudioDatabase()
            except RuntimeError:
                db = StudioDatabase(":memory:")
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
    app.state.registry = registry
    app.state.preview_reg = preview_reg
    app.state.db = db

    app.add_middleware(BasicAuthMiddleware)
    if getattr(registry, "preview_registry", None) is None:
        registry.preview_registry = preview_reg

    STATIC_DIST_DIR.mkdir(parents=True, exist_ok=True)
    assets_dir = STATIC_DIST_DIR / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
    app.mount("/static/dist", StaticFiles(directory=str(STATIC_DIST_DIR)), name="static_dist")

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

    # Mount decomposed route modules
    app.include_router(repos_router)
    app.include_router(jobs_router)
    app.include_router(preview_router)
    app.include_router(chat_router)
    app.include_router(pulls_router)
    app.include_router(rollback_router)
    app.include_router(files_router)

    return app
