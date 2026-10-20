"""Hybrid file tree discovery and source code retrieval routes."""

import base64
import json
import os
from pathlib import Path
import shlex
import sys
from typing import Any
import httpx

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

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


def _get_preview_reg(request: Request) -> PreviewRegistry:
    return getattr(request.app.state, "preview_reg", preview_registry)


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

    target_branch = branch.strip() if branch and branch.strip() else None
    if not target_branch:
        preview = preview_reg.get_preview(bare_repo) or preview_reg.get_preview(clean_repo)
        if preview and preview.branch:
            target_branch = preview.branch
        else:
            target_branch = resolve_active_preview_branch(bare_repo)

    active_sandbox, _ = preview_reg.get_active_sandbox(bare_repo)
    if active_sandbox is None:
        active_sandbox, _ = preview_reg.get_active_sandbox(clean_repo)

    # 1. Live Unified Studio Sandbox active
    if active_sandbox is not None:
        tree_script = (
            f"python3 -c "
            f"\"import os, json; "
            f"root = '/root/{bare_repo}'; "
            f"ignored = {list(IGNORED_DIRECTORIES)}; "
            f"results = []; "
            f"exists = os.path.isdir(root); "
            f"if exists: "
            f"    for dirpath, dirnames, filenames in os.walk(root): "
            f"        dirnames[:] = [d for d in dirnames if d not in ignored and not any(p in ignored for p in d.split('/'))]; "
            f"        rel_dir = os.path.relpath(dirpath, root); "
            f"        if rel_dir != '.': "
            f"            results.append({{'path': rel_dir.replace('\\\\', '/'), 'type': 'tree', 'size': 0}}); "
            f"        for f in filenames: "
            f"            if f in ignored: continue; "
            f"            rel_path = os.path.normpath(os.path.join(rel_dir, f)).replace('\\\\', '/') if rel_dir != '.' else f; "
            f"            full_path = os.path.join(dirpath, f); "
            f"            try: sz = os.path.getsize(full_path); "
            f"            except Exception: sz = 0; "
            f"            results.append({{'path': rel_path, 'type': 'blob', 'size': sz}}); "
            f"results.sort(key=lambda x: x['path']); "
            f"print(json.dumps(results))\""
        )
        proc = active_sandbox.exec("bash", "-c", tree_script)
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
    auth_token = get_test_org_token()
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SoftwareFactory-TestingConsole/1.0",
    }
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

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
    target_branch = branch.strip() if branch and branch.strip() else None
    if not target_branch:
        preview = preview_reg.get_preview(bare_repo) or preview_reg.get_preview(clean_repo)
        if preview and preview.branch:
            target_branch = preview.branch
        else:
            target_branch = resolve_active_preview_branch(bare_repo)

    active_sandbox, _ = preview_reg.get_active_sandbox(bare_repo)
    if active_sandbox is None:
        active_sandbox, _ = preview_reg.get_active_sandbox(clean_repo)

    lang = detect_language(clean_path)

    # 1. Live Sandbox Inspection
    if active_sandbox is not None:
        file_script = (
            f"python3 -c "
            f"\"import os, json; "
            f"target = os.path.join('/root/{bare_repo}', {shlex.quote(clean_path)}); "
            f"if not os.path.isfile(target): "
            f"    print(json.dumps({{'exists': False}})); "
            f"else: "
            f"    sz = os.path.getsize(target); "
            f"    if sz > {MAX_FILE_SIZE_BYTES}: "
            f"        print(json.dumps({{'exists': True, 'size': sz, 'is_binary': False, 'is_truncated': True, 'content': None}})); "
            f"    else: "
            f"        is_bin = False; "
            f"        with open(target, 'rb') as f: "
            f"            chunk = f.read(8192); "
            f"            if b'\\x00' in chunk: is_bin = True; "
            f"        if is_bin: "
            f"            print(json.dumps({{'exists': True, 'size': sz, 'is_binary': True, 'is_truncated': False, 'content': None}})); "
            f"        else: "
            f"            with open(target, 'r', encoding='utf-8', errors='replace') as f: "
            f"                cnt = f.read(); "
            f"            print(json.dumps({{'exists': True, 'size': sz, 'is_binary': False, 'is_truncated': False, 'content': cnt}}))\""
        )
        proc = active_sandbox.exec("bash", "-c", file_script)
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
            "source": "sandbox",
        }

    # 2. GitHub Contents API fallback
    auth_token = get_test_org_token()
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SoftwareFactory-TestingConsole/1.0",
    }
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

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
                    "source": "github",
                }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch file from GitHub: {str(exc)}")

    raise HTTPException(status_code=404, detail=f"File not found: {clean_path}")
