"""FastAPI routes for Visual QA telemetry metadata and screenshot artifacts."""

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from factory.ui.github import strip_repo_owner
from factory.ui.registry import JobRegistry, job_registry

router = APIRouter()


class VisualQaTelemetryResponse(BaseModel):
    """Structured response model for Visual QA telemetry and screenshot artifacts."""

    passed: bool = Field(..., description="Whether visual verification passed")
    status: str = Field(..., description="Verification status: passed, failed, or pending")
    errors: list[str] = Field(default_factory=list, description="Visual QA runtime or canvas errors")
    desktop_url: str | None = Field(None, description="URL for desktop viewport screenshot")
    mobile_url: str | None = Field(None, description="URL for mobile viewport screenshot")
    captured_at: float | None = Field(None, description="Timestamp of visual verification capture")


def _get_registry(request: Request) -> JobRegistry:
    return getattr(request.app.state, "registry", job_registry)


def _get_base_artifacts_dir() -> Path:
    env_dir = os.environ.get("FACTORY_ARTIFACTS_DIR")
    if env_dir:
        return Path(env_dir)
    return Path("/root/.factory/artifacts")


def _get_candidate_vqa_dirs(repo: str, branch: str | None = None) -> list[Path]:
    base_dir = _get_base_artifacts_dir()
    clean_repo = strip_repo_owner(repo)

    candidates: list[Path] = []
    if branch:
        clean_branch = branch.replace("/", "-")
        candidates.append(base_dir / clean_repo / clean_branch / "visual-qa")
        candidates.append(base_dir / clean_repo / branch / "visual-qa")
        candidates.append(base_dir / clean_branch / "visual-qa")
        candidates.append(base_dir / branch / "visual-qa")
        candidates.append(base_dir / clean_repo / "visual-qa" / clean_branch)
        candidates.append(base_dir / clean_repo / "visual-qa" / branch)
        candidates.append(base_dir / "visual-qa" / clean_branch)
        candidates.append(base_dir / "visual-qa" / branch)

    candidates.append(base_dir / clean_repo / "visual-qa")
    candidates.append(base_dir / repo / "visual-qa")
    candidates.append(base_dir / "visual-qa")
    candidates.append(Path.cwd() / "artifacts" / "visual-qa")
    candidates.append(Path("/tmp/factory/artifacts") / "visual-qa")
    return candidates


def _find_screenshot_file(
    repo: str,
    branch: str | None,
    viewport: str,
    registry: JobRegistry,
) -> Path | None:
    norm_viewport = viewport.lower().strip()
    if not norm_viewport.endswith(".png"):
        filename = f"{norm_viewport}.png"
    else:
        filename = norm_viewport

    candidate_dirs = _get_candidate_vqa_dirs(repo, branch)
    for vqa_dir in candidate_dirs:
        candidate_file = vqa_dir / filename
        if candidate_file.is_file():
            return candidate_file

    if hasattr(registry, "get_latest_visual_qa_event"):
        event = registry.get_latest_visual_qa_event(repo, branch=branch)
        if event:
            data = event.get("data", {})
            screenshots = data.get("screenshots") or {}
            vp_key = "desktop" if "desk" in norm_viewport else "mobile"
            shot_path_str = screenshots.get(vp_key)
            if shot_path_str:
                shot_path = Path(shot_path_str)
                if shot_path.is_file():
                    return shot_path

    return None


@router.get("/api/studio/repos/{repo}/visual-qa", response_model=VisualQaTelemetryResponse)
@router.get("/api/repos/{repo}/visual-qa", response_model=VisualQaTelemetryResponse)
async def get_visual_qa_telemetry(
    repo: str,
    request: Request,
    branch: str | None = Query(None, description="Optional target branch"),
) -> VisualQaTelemetryResponse:
    """Returns the latest captured Visual QA telemetry metadata for a repository and branch."""
    registry = _get_registry(request)
    candidate_dirs = _get_candidate_vqa_dirs(repo, branch)

    prefix = (
        f"/api/studio/repos/{repo}/visual-qa/screenshot"
        if request.url.path.startswith("/api/studio")
        else f"/api/repos/{repo}/visual-qa/screenshot"
    )

    def _make_urls(has_desktop: bool, has_mobile: bool) -> tuple[str | None, str | None]:
        b_query = f"&branch={branch}" if branch else ""
        d_url = f"{prefix}?viewport=desktop{b_query}" if has_desktop else None
        m_url = f"{prefix}?viewport=mobile{b_query}" if has_mobile else None
        return d_url, m_url

    # 1. Search candidate artifact directories on disk
    for vqa_dir in candidate_dirs:
        meta_file = vqa_dir / "metadata.json"
        if meta_file.is_file():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                passed = bool(meta.get("passed", False))
                status = str(meta.get("status") or ("passed" if passed else "failed"))
                raw_errors = meta.get("errors", [])
                errors = [e.get("message", str(e)) if isinstance(e, dict) else str(e) for e in raw_errors]
                captured_at = meta.get("captured_at") or meta.get("timestamp")

                has_desktop = (vqa_dir / "desktop.png").is_file() or bool(meta.get("screenshots", {}).get("desktop"))
                has_mobile = (vqa_dir / "mobile.png").is_file() or bool(meta.get("screenshots", {}).get("mobile"))
                desktop_url, mobile_url = _make_urls(has_desktop, has_mobile)

                return VisualQaTelemetryResponse(
                    passed=passed,
                    status=status,
                    errors=errors,
                    desktop_url=desktop_url,
                    mobile_url=mobile_url,
                    captured_at=float(captured_at) if captured_at is not None else None,
                )
            except Exception:
                pass

        desktop_file = vqa_dir / "desktop.png"
        mobile_file = vqa_dir / "mobile.png"
        if desktop_file.is_file() or mobile_file.is_file():
            mtime = desktop_file.stat().st_mtime if desktop_file.is_file() else mobile_file.stat().st_mtime
            desktop_url, mobile_url = _make_urls(desktop_file.is_file(), mobile_file.is_file())
            return VisualQaTelemetryResponse(
                passed=True,
                status="passed",
                errors=[],
                desktop_url=desktop_url,
                mobile_url=mobile_url,
                captured_at=float(mtime),
            )

    # 2. Check JobRegistry events for recorded telemetry
    if hasattr(registry, "get_latest_visual_qa_event"):
        event = registry.get_latest_visual_qa_event(repo, branch=branch)
        if event:
            data = event.get("data", {})
            passed = bool(data.get("passed", False))
            status = "passed" if passed else "failed"
            raw_errors = data.get("errors", [])
            errors = [e.get("message", str(e)) if isinstance(e, dict) else str(e) for e in raw_errors]
            captured_at = event.get("timestamp")

            shots = data.get("screenshots") or {}
            has_desktop = bool(shots.get("desktop"))
            has_mobile = bool(shots.get("mobile"))
            desktop_url, mobile_url = _make_urls(has_desktop, has_mobile)

            return VisualQaTelemetryResponse(
                passed=passed,
                status=status,
                errors=errors,
                desktop_url=desktop_url,
                mobile_url=mobile_url,
                captured_at=float(captured_at) if captured_at is not None else None,
            )

    # 3. Default pending state
    return VisualQaTelemetryResponse(
        passed=False,
        status="pending",
        errors=[],
        desktop_url=None,
        mobile_url=None,
        captured_at=None,
    )


@router.get("/api/studio/repos/{repo}/visual-qa/screenshot")
@router.get("/api/repos/{repo}/visual-qa/screenshot")
async def get_visual_qa_screenshot(
    repo: str,
    request: Request,
    branch: str | None = Query(None, description="Optional target branch"),
    viewport: str = Query("desktop", description="Viewport: desktop or mobile"),
):
    """Serves the captured PNG screenshot for the requested viewport and repository."""
    registry = _get_registry(request)
    screenshot_file = _find_screenshot_file(repo, branch, viewport, registry)

    if not screenshot_file or not screenshot_file.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Visual QA screenshot not found for repo '{repo}' (viewport: {viewport})",
        )

    return FileResponse(str(screenshot_file), media_type="image/png")
