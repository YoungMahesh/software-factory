"""Hybrid file tree discovery and source code retrieval routes."""

import base64
import json
import os
from pathlib import Path
import sys
from typing import Any
import httpx

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response

from factory.ui.github import DEFAULT_TEST_ORG, get_test_org_token, strip_repo_owner
from factory.ui.registry import (
    PreviewRegistry,
    preview_registry,
    resolve_active_preview_branch,
)

router = APIRouter()

MAX_FILE_SIZE_BYTES = 500 * 1024  # 500KB inspection ceiling

IGNORED_DIRECTORIES = {
    "node_modules",
    ".git",
    ".venv",
    "venv",
    ".next",
    "dist",
    "build",
    "__pycache__",
    ".turbo",
    ".cache",
    ".output",
    ".nuxt",
}

EXTENSION_TO_LANGUAGE = {
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".json": "json",
    ".py": "python",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".md": "markdown",
    ".sh": "bash",
    ".bash": "bash",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".toml": "toml",
    ".sql": "sql",
    ".xml": "xml",
    ".svg": "xml",
    ".rs": "rust",
    ".go": "go",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".dockerfile": "dockerfile",
}


def _get_preview_reg(request: Request | None) -> PreviewRegistry:
    if request is not None and hasattr(request, "app"):
        return getattr(request.app.state, "preview_reg", preview_registry)
    return preview_registry


def _get_active_sandbox(request: Request | None, clean_repo: str, bare_repo: str) -> tuple[Any, str | None]:
    preview_reg = _get_preview_reg(request)
    for r in (bare_repo, clean_repo):
        sandbox, url = preview_reg.get_active_sandbox(r)
        if sandbox is not None:
            return sandbox, url
    return None, None


def _resolve_target_branch(
    preview_reg: PreviewRegistry,
    clean_repo: str,
    bare_repo: str,
    branch: str | None,
) -> str:
    if branch and branch.strip():
        return branch.strip()
    preview = preview_reg.get_preview(bare_repo) or preview_reg.get_preview(clean_repo)
    if preview and preview.branch:
        return preview.branch
    return resolve_active_preview_branch(bare_repo)


def _get_github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SoftwareFactory-TestingConsole/1.0",
    }
    token = get_test_org_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def is_ignored_path(path: str) -> bool:
    """Checks whether any segment of path matches the server-side ignored directories."""
    clean = path.strip("/\\")
    if not clean:
        return False
    parts = clean.replace("\\", "/").split("/")
    return any(p in IGNORED_DIRECTORIES for p in parts)


def detect_language(path: str) -> str:
    """Detects syntax highlighting language from file name or extension."""
    ext = Path(path).suffix.lower()
    name = Path(path).name.lower()
    if name == "dockerfile":
        return "dockerfile"
    return EXTENSION_TO_LANGUAGE.get(ext, "plaintext")


def validate_relative_path(path: str) -> None:
    """Validates that path does not attempt directory traversal or access restricted directories."""
    clean = path.strip()
    if not clean or clean.startswith("/") or clean.startswith("\\"):
        raise HTTPException(status_code=400, detail="Invalid relative path.")
    norm = os.path.normpath(clean)
    if norm.startswith("..") or "/../" in norm or norm == "..":
        raise HTTPException(status_code=400, detail="Path traversal is not permitted.")
    if is_ignored_path(norm):
        raise HTTPException(
            status_code=403,
            detail=f"Access to restricted directory is prohibited: {norm}",
        )


def _read_process_output(proc: Any) -> str:
    """Collects stdout string from a sandbox process execution handle."""
    stdout_reader = getattr(proc, "stdout", None)
    if stdout_reader is None:
        return ""
    lines: list[str] = []
    try:
        for chunk in stdout_reader:
            text = chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else str(chunk)
            lines.append(text)
    except Exception:
        pass
    if hasattr(proc, "wait"):
        try:
            proc.wait()
        except Exception:
            pass
    return "".join(lines)


@router.get("/api/repos/{repo}/tree")
async def get_repo_tree(
    repo: str,
    request: Request,
    branch: str | None = Query(None, description="Target branch (defaults to active preview branch or main)"),
):
    """Hybrid file tree discovery: queries live sandbox when active, falls back to GitHub Git Database API."""
    clean_repo = repo.strip()
    bare_repo = strip_repo_owner(clean_repo)
    preview_reg = _get_preview_reg(request)
    target_branch = _resolve_target_branch(preview_reg, clean_repo, bare_repo, branch)
    active_sandbox, _ = _get_active_sandbox(request, clean_repo, bare_repo)

    # 1. Live Unified Studio Sandbox active
    if active_sandbox is not None:
        tree_py = (
            "import os, sys, json\n"
            "bare_repo = sys.argv[1]\n"
            "root = os.path.join('/root', bare_repo)\n"
            f"ignored = set({list(IGNORED_DIRECTORIES)})\n"
            "results = []\n"
            "if os.path.isdir(root):\n"
            "    for dirpath, dirnames, filenames in os.walk(root):\n"
            "        dirnames[:] = [d for d in dirnames if d not in ignored and not any(p in ignored for p in d.split('/'))]\n"
            "        rel_dir = os.path.relpath(dirpath, root)\n"
            "        if rel_dir != '.':\n"
            "            results.append({'path': rel_dir.replace('\\\\', '/'), 'type': 'tree', 'size': 0})\n"
            "        for f in filenames:\n"
            "            if f in ignored: continue\n"
            "            rel_path = os.path.normpath(os.path.join(rel_dir, f)).replace('\\\\', '/') if rel_dir != '.' else f\n"
            "            full_path = os.path.join(dirpath, f)\n"
            "            try: sz = os.path.getsize(full_path)\n"
            "            except Exception: sz = 0\n"
            "            results.append({'path': rel_path, 'type': 'blob', 'size': sz})\n"
            "results.sort(key=lambda x: x['path'])\n"
            "print(json.dumps(results))\n"
        )
        proc = active_sandbox.exec("python3", "-c", tree_py, bare_repo)
        raw_output = _read_process_output(proc).strip()
        try:
            tree_data = json.loads(raw_output) if raw_output else []
        except Exception:
            tree_data = []

        return {
            "repo": bare_repo,
            "branch": target_branch,
            "tree": tree_data,
            "source": "sandbox",
        }

    # 2. Remote GitHub Git Database API fallback
    headers = _get_github_headers()
    tree_url = f"https://api.github.com/repos/{DEFAULT_TEST_ORG}/{bare_repo}/git/trees/{target_branch}?recursive=1"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(tree_url, headers=headers)
            if resp.status_code == 200:
                raw_payload = resp.json()
                raw_tree = raw_payload.get("tree", []) if isinstance(raw_payload, dict) else []
                filtered_tree = [
                    {
                        "path": item.get("path"),
                        "type": item.get("type"),
                        "size": item.get("size", 0),
                    }
                    for item in raw_tree
                    if isinstance(item, dict) and item.get("path") and not is_ignored_path(item["path"])
                ]
                return {
                    "repo": bare_repo,
                    "branch": target_branch,
                    "tree": filtered_tree,
                    "source": "github",
                }
    except Exception:
        pass

    return {
        "repo": bare_repo,
        "branch": target_branch,
        "tree": [],
        "source": "github",
    }


@router.get("/api/repos/{repo}/files")
async def get_repo_file(
    repo: str,
    path: str = Query(..., description="Relative file path to inspect (e.g. 'src/App.tsx')"),
    request: Request = None,
    branch: str | None = Query(None, description="Target branch (defaults to active preview branch or main)"),
):
    """Hybrid file content retrieval: inspects live sandbox when active, falls back to GitHub API."""
    clean_repo = repo.strip()
    bare_repo = strip_repo_owner(clean_repo)
    clean_path = path.strip()
    validate_relative_path(clean_path)

    preview_reg = _get_preview_reg(request)
    target_branch = _resolve_target_branch(preview_reg, clean_repo, bare_repo, branch)
    active_sandbox, _ = _get_active_sandbox(request, clean_repo, bare_repo)
    lang = detect_language(clean_path)
    download_url = f"/api/repos/{bare_repo}/raw?path={clean_path}&branch={target_branch}"

    # 1. Live Sandbox Inspection
    if active_sandbox is not None:
        file_py = (
            "import os, sys, json\n"
            "bare_repo = sys.argv[1]\n"
            "clean_path = sys.argv[2]\n"
            f"max_bytes = {MAX_FILE_SIZE_BYTES}\n"
            "target = os.path.join('/root', bare_repo, clean_path)\n"
            "if not os.path.isfile(target):\n"
            "    print(json.dumps({'exists': False}))\n"
            "else:\n"
            "    sz = os.path.getsize(target)\n"
            "    if sz > max_bytes:\n"
            "        print(json.dumps({'exists': True, 'size': sz, 'is_binary': False, 'is_truncated': True, 'content': None}))\n"
            "    else:\n"
            "        is_bin = False\n"
            "        with open(target, 'rb') as f:\n"
            "            chunk = f.read(8192)\n"
            "            if b'\\x00' in chunk: is_bin = True\n"
            "        if is_bin:\n"
            "            print(json.dumps({'exists': True, 'size': sz, 'is_binary': True, 'is_truncated': False, 'content': None}))\n"
            "        else:\n"
            "            with open(target, 'r', encoding='utf-8', errors='replace') as f:\n"
            "                cnt = f.read()\n"
            "            print(json.dumps({'exists': True, 'size': sz, 'is_binary': False, 'is_truncated': False, 'content': cnt}))\n"
        )
        proc = active_sandbox.exec("python3", "-c", file_py, bare_repo, clean_path)
        raw_output = _read_process_output(proc).strip()
        data: dict[str, Any] = {}
        try:
            data = json.loads(raw_output) if raw_output else {}
        except Exception:
            pass

        if not data.get("exists", False):
            raise HTTPException(status_code=404, detail=f"File not found in sandbox: {clean_path}")

        sz = data.get("size", 0)
        is_bin = data.get("is_binary", False)
        is_trunc = data.get("is_truncated", False) or sz > MAX_FILE_SIZE_BYTES
        content = None if (is_bin or is_trunc) else data.get("content")

        message = None
        if is_trunc:
            message = f"File exceeds 500KB inspection ceiling ({sz / 1024:.1f} KB)."
        elif is_bin:
            message = "Binary file cannot be displayed."

        return {
            "repo": bare_repo,
            "branch": target_branch,
            "path": clean_path,
            "size": sz,
            "is_binary": is_bin,
            "is_truncated": is_trunc,
            "content": content,
            "language": lang,
            "message": message,
            "download_url": download_url,
            "source": "sandbox",
        }

    # 2. GitHub Contents / Blobs API fallback
    headers = _get_github_headers()
    content_url = f"https://api.github.com/repos/{DEFAULT_TEST_ORG}/{bare_repo}/contents/{clean_path}?ref={target_branch}"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(content_url, headers=headers)
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail=f"File not found on branch {target_branch}: {clean_path}")
            if resp.status_code == 200:
                payload = resp.json()
                sz = payload.get("size", 0)
                if sz > MAX_FILE_SIZE_BYTES:
                    return {
                        "repo": bare_repo,
                        "branch": target_branch,
                        "path": clean_path,
                        "size": sz,
                        "is_binary": False,
                        "is_truncated": True,
                        "content": None,
                        "language": lang,
                        "message": f"File exceeds 500KB inspection ceiling ({sz / 1024:.1f} KB).",
                        "download_url": download_url,
                        "source": "github",
                    }

                b64_content = payload.get("content", "")
                raw_bytes = base64.b64decode(b64_content) if b64_content else b""
                is_bin = b"\x00" in raw_bytes[:8192]
                if is_bin:
                    return {
                        "repo": bare_repo,
                        "branch": target_branch,
                        "path": clean_path,
                        "size": sz,
                        "is_binary": True,
                        "is_truncated": False,
                        "content": None,
                        "language": lang,
                        "message": "Binary file cannot be displayed.",
                        "download_url": download_url,
                        "source": "github",
                    }

                text_content = raw_bytes.decode("utf-8", errors="replace")
                return {
                    "repo": bare_repo,
                    "branch": target_branch,
                    "path": clean_path,
                    "size": sz,
                    "is_binary": False,
                    "is_truncated": False,
                    "content": text_content,
                    "language": lang,
                    "message": None,
                    "download_url": download_url,
                    "source": "github",
                }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch file from GitHub: {str(exc)}")

    raise HTTPException(status_code=404, detail=f"File not found: {clean_path}")


@router.get("/api/repos/{repo}/raw")
async def get_repo_raw_file(
    repo: str,
    path: str = Query(..., description="Relative file path to download"),
    request: Request = None,
    branch: str | None = Query(None, description="Target branch"),
):
    """Raw file download endpoint for binary assets or large files exceeding preview limits."""
    clean_repo = repo.strip()
    bare_repo = strip_repo_owner(clean_repo)
    clean_path = path.strip()
    validate_relative_path(clean_path)

    preview_reg = _get_preview_reg(request)
    target_branch = _resolve_target_branch(preview_reg, clean_repo, bare_repo, branch)
    active_sandbox, _ = _get_active_sandbox(request, clean_repo, bare_repo)
    filename = Path(clean_path).name

    # 1. Live Sandbox Raw Retrieval
    if active_sandbox is not None:
        read_py = (
            "import os, sys, base64\n"
            "target = os.path.join('/root', sys.argv[1], sys.argv[2])\n"
            "if os.path.isfile(target):\n"
            "    with open(target, 'rb') as f:\n"
            "        sys.stdout.buffer.write(base64.b64encode(f.read()))\n"
        )
        proc = active_sandbox.exec("python3", "-c", read_py, bare_repo, clean_path)
        raw_b64 = _read_process_output(proc).strip().encode("utf-8")
        if not raw_b64:
            raise HTTPException(status_code=404, detail=f"File not found in sandbox: {clean_path}")
        file_bytes = base64.b64decode(raw_b64)
        return Response(
            content=file_bytes,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # 2. GitHub Raw Retrieval
    headers = _get_github_headers()
    content_url = f"https://api.github.com/repos/{DEFAULT_TEST_ORG}/{bare_repo}/contents/{clean_path}?ref={target_branch}"
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(content_url, headers=headers)
            if resp.status_code == 200:
                payload = resp.json()
                b64_content = payload.get("content", "")
                file_bytes = base64.b64decode(b64_content) if b64_content else b""
                return Response(
                    content=file_bytes,
                    media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'},
                )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch raw file: {str(exc)}")

    raise HTTPException(status_code=404, detail=f"File not found: {clean_path}")
