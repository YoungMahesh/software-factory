"""Studio Turn Rollback router and in-container Git revert execution."""

import concurrent.futures
import re
import shlex
import sys
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from factory.ui.db import StudioDatabase
import factory.ui.github as gh
from factory.ui.registry import (
    JobRegistry,
    job_registry,
    PreviewRegistry,
    preview_registry,
    PreviewStatus,
)
from factory.ui.tracker import update_local_markdown_issue_for_rollback

router = APIRouter()


class RollbackTurnRequest(BaseModel):
    message_id: str | None = Field(None, description="Optional target assistant message ID to roll back")
    branch: str | None = Field(None, description="Optional target branch to roll back (defaults to active preview branch)")


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


def _execute_in_sandbox_rollback(
    active_sandbox: Any,
    clean_repo: str,
    bare_repo: str,
    target_branch: str,
    commit_sha: str | None,
    preview_reg: PreviewRegistry,
) -> tuple[str, str]:
    """Executes in-container git revert --no-edit, pushes to remote, and runs diff-aware pnpm install."""
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


@router.post("/api/repos/{repo}/rollback")
async def rollback_turn_endpoint(repo: str, request: Request, req: RollbackTurnRequest | None = None):
    clean_repo = repo.strip()
    if not clean_repo:
        raise HTTPException(status_code=400, detail="Repository name is required.")

    registry = _get_registry(request)
    preview_reg = _get_preview_reg(request)
    db = _get_db(request)

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

    fetch_prs_fn = _gh("fetch_repo_pull_requests")
    prs = fetch_prs_fn(clean_repo, branch=target_branch, state="all")
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
        preview_reg=preview_reg,
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
            reopen_fn = _gh("reopen_repo_issue_for_rollback")
            reopen_fn(
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
