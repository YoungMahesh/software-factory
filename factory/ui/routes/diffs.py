"""Pre-Merge Diff Viewer backend endpoints with dual-scope comparison."""

import json
import re
from typing import Any
import httpx

from fastapi import APIRouter, HTTPException, Query, Request

from factory.ui.github import DEFAULT_TEST_ORG, get_test_org_token, strip_repo_owner
from factory.ui.registry import (
    PreviewRegistry,
    preview_registry,
    resolve_active_preview_branch,
)
from factory.ui.routes.files import (
    _get_active_sandbox,
    _get_github_headers,
    _get_preview_reg,
    _read_process_output,
    _resolve_target_branch,
    is_ignored_path,
)

router = APIRouter()


def _parse_unified_git_diff(raw_diff: str) -> list[dict[str, Any]]:
    """Parses a multi-file unified git diff string into structured file items."""
    if not raw_diff or not raw_diff.strip():
        return []

    chunks = re.split(r"(?=^diff --git )", raw_diff, flags=re.MULTILINE)
    files: list[dict[str, Any]] = []

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk or not chunk.startswith("diff --git"):
            continue

        lines = chunk.splitlines()
        first_line = lines[0]
        # diff --git a/path/to/file b/path/to/file
        m = re.match(r"^diff --git a/(.*?) b/(.*?)$", first_line)
        if m:
            old_path, new_path = m.group(1), m.group(2)
        else:
            old_path, new_path = "", ""

        status = "modified"
        if "new file mode" in chunk:
            status = "added"
        elif "deleted file mode" in chunk:
            status = "deleted"
        elif "rename from" in chunk or "similarity index" in chunk:
            status = "renamed"

        target_path = new_path or old_path
        if not target_path or is_ignored_path(target_path):
            continue

        additions = 0
        deletions = 0
        patch_lines: list[str] = []
        in_patch = False

        for line in lines:
            if line.startswith("@@"):
                in_patch = True
            if in_patch:
                patch_lines.append(line)
                if line.startswith("+") and not line.startswith("+++ "):
                    additions += 1
                elif line.startswith("-") and not line.startswith("--- "):
                    deletions += 1

        files.append(
            {
                "path": target_path,
                "old_path": old_path if old_path != target_path else None,
                "status": status,
                "additions": additions,
                "deletions": deletions,
                "patch": "\n".join(patch_lines) if patch_lines else chunk,
            }
        )

    return files


def _build_untracked_file_diff(path: str, content: str) -> dict[str, Any]:
    """Builds a synthetic unified diff entry for an untracked added file."""
    lines = content.splitlines()
    line_count = len(lines)
    patch_lines = [f"@@ -0,0 +1,{max(1, line_count)} @@"]
    for l in lines:
        patch_lines.append(f"+{l}")
    patch_str = "\n".join(patch_lines)

    return {
        "path": path,
        "old_path": None,
        "status": "added",
        "additions": line_count,
        "deletions": 0,
        "patch": patch_str,
    }


def _build_diff_response(
    bare_repo: str,
    target_branch: str,
    base: str,
    scope: str,
    source: str,
    file_diffs: list[dict[str, Any]],
    message: str | None = None,
) -> dict[str, Any]:
    """Constructs standardized diff response dictionary with addition/deletion summary."""
    total_adds = sum(f["additions"] for f in file_diffs)
    total_dels = sum(f["deletions"] for f in file_diffs)
    return {
        "repo": bare_repo,
        "branch": target_branch,
        "base": base,
        "scope": scope,
        "source": source,
        "summary": {
            "total_files": len(file_diffs),
            "additions": total_adds,
            "deletions": total_dels,
        },
        "files": file_diffs,
        "clean": len(file_diffs) == 0,
        "message": message,
    }


@router.get("/api/repos/{repo}/diff")
async def get_repo_diff(
    repo: str,
    request: Request,
    scope: str = Query("working_tree", description="Comparison scope: 'working_tree' or 'branch'"),
    branch: str | None = Query(None, description="Target feature branch"),
    base: str = Query("main", description="Base trunk branch for branch comparison"),
):
    """Retrieves multi-file diffs supporting working tree and branch comparison scopes."""
    clean_repo = repo.strip()
    bare_repo = strip_repo_owner(clean_repo)
    preview_reg = _get_preview_reg(request)
    target_branch = _resolve_target_branch(preview_reg, clean_repo, bare_repo, branch)
    active_sandbox, _ = _get_active_sandbox(request, clean_repo, bare_repo)

    norm_scope = "branch" if scope.lower() in ("branch", "feature_branch") else "working_tree"

    # 1. Working Tree Scope (Container uncommitted edits vs HEAD)
    if norm_scope == "working_tree":
        if active_sandbox is None:
            return _build_diff_response(
                bare_repo=bare_repo,
                target_branch=target_branch,
                base=base,
                scope="working_tree",
                source="sandbox",
                file_diffs=[],
                message="Unified Studio Sandbox is not running.",
            )

        diff_py = (
            "import os, sys, json, subprocess\n"
            "bare_repo = sys.argv[1]\n"
            "root = os.path.join('/root', bare_repo)\n"
            "result = {'diff': '', 'untracked': []}\n"
            "if os.path.isdir(root):\n"
            "    try:\n"
            "        p = subprocess.run(['git', 'diff', '-U3', 'HEAD'], cwd=root, capture_output=True, text=True, timeout=10)\n"
            "        result['diff'] = p.stdout\n"
            "    except Exception:\n"
            "        pass\n"
            "    try:\n"
            "        st = subprocess.run(['git', 'status', '--porcelain'], cwd=root, capture_output=True, text=True, timeout=10)\n"
            "        for line in st.stdout.splitlines():\n"
            "            if line.startswith('?? '):\n"
            "                rel = line[3:].strip()\n"
            "                full = os.path.join(root, rel)\n"
            "                if os.path.isfile(full) and os.path.getsize(full) <= 200 * 1024:\n"
            "                    try:\n"
            "                        with open(full, 'r', encoding='utf-8', errors='replace') as f:\n"
            "                            cnt = f.read()\n"
            "                        result['untracked'].append({'path': rel.replace('\\\\', '/'), 'content': cnt})\n"
            "                    except Exception:\n"
            "                        pass\n"
            "    except Exception:\n"
            "        pass\n"
            "print(json.dumps(result))\n"
        )
        proc = active_sandbox.exec("python3", "-c", diff_py, bare_repo)
        raw_output = _read_process_output(proc).strip()
        data: dict[str, Any] = {}
        try:
            data = json.loads(raw_output) if raw_output else {}
        except Exception:
            data = {}

        raw_diff = data.get("diff", "")
        file_diffs = _parse_unified_git_diff(raw_diff)

        seen_paths = {f["path"] for f in file_diffs}
        untracked = data.get("untracked", [])
        for u in untracked:
            u_path = u.get("path", "")
            if u_path and not is_ignored_path(u_path) and u_path not in seen_paths:
                file_diffs.append(_build_untracked_file_diff(u_path, u.get("content", "")))
                seen_paths.add(u_path)

        return _build_diff_response(
            bare_repo=bare_repo,
            target_branch=target_branch,
            base=base,
            scope="working_tree",
            source="sandbox",
            file_diffs=file_diffs,
        )

    # 2. Branch Scope (Feature branch vs main trunk)
    # Check if sandbox can execute git diff origin/{base}...{branch}
    if active_sandbox is not None:
        branch_diff_py = (
            "import os, sys, json, subprocess\n"
            "bare_repo = sys.argv[1]\n"
            "base_br = sys.argv[2]\n"
            "target_br = sys.argv[3]\n"
            "root = os.path.join('/root', bare_repo)\n"
            "result = {'diff': '', 'success': False}\n"
            "if os.path.isdir(root):\n"
            "    targets = [f'origin/{base_br}...origin/{target_br}', f'origin/{base_br}...{target_br}', f'origin/{base_br}...HEAD', f'{base_br}...HEAD']\n"
            "    for target in targets:\n"
            "        try:\n"
            "            p = subprocess.run(['git', 'diff', '-U3', target], cwd=root, capture_output=True, text=True, timeout=10)\n"
            "            if p.returncode == 0:\n"
            "                result['diff'] = p.stdout\n"
            "                result['success'] = True\n"
            "                break\n"
            "        except Exception:\n"
            "            pass\n"
            "print(json.dumps(result))\n"
        )
        proc = active_sandbox.exec("python3", "-c", branch_diff_py, bare_repo, base, target_branch)
        raw_output = _read_process_output(proc).strip()
        data = {}
        try:
            data = json.loads(raw_output) if raw_output else {}
        except Exception:
            data = {}

        if data.get("success", False):
            file_diffs = _parse_unified_git_diff(data.get("diff", ""))
            return _build_diff_response(
                bare_repo=bare_repo,
                target_branch=target_branch,
                base=base,
                scope="branch",
                source="sandbox",
                file_diffs=file_diffs,
            )

    # Fallback to GitHub Comparison API
    headers = _get_github_headers()
    compare_url = f"https://api.github.com/repos/{DEFAULT_TEST_ORG}/{bare_repo}/compare/{base}...{target_branch}"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(compare_url, headers=headers)
            if resp.status_code == 200:
                payload = resp.json()
                raw_files = payload.get("files", []) if isinstance(payload, dict) else []
                filtered_files: list[dict[str, Any]] = []

                for item in raw_files:
                    fn = item.get("filename", "")
                    if not fn or is_ignored_path(fn):
                        continue
                    status_raw = item.get("status", "modified")
                    status = "deleted" if status_raw == "removed" else status_raw

                    filtered_files.append(
                        {
                            "path": fn,
                            "old_path": item.get("previous_filename"),
                            "status": status,
                            "additions": item.get("additions", 0),
                            "deletions": item.get("deletions", 0),
                            "patch": item.get("patch", ""),
                        }
                    )

                return _build_diff_response(
                    bare_repo=bare_repo,
                    target_branch=target_branch,
                    base=base,
                    scope="branch",
                    source="github",
                    file_diffs=filtered_files,
                )
    except Exception:
        pass

    return _build_diff_response(
        bare_repo=bare_repo,
        target_branch=target_branch,
        base=base,
        scope="branch",
        source="github",
        file_diffs=[],
    )
