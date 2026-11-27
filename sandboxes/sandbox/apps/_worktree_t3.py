"""T3 worktree thread launch, polling, conditional dependency install, and prompt dispatch."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

from ._models import FactoryAppRecord, build_initial_thread_prompt
from ._prompts import GENERIC_REPO_OPEN_PROMPT, derive_worktree_branch
from ._workspace import exec_in_sandbox, install_repo_dependencies_in_sandbox

logger = logging.getLogger(__name__)

_MCP_WORKTREE_LAUNCH_NODE_SCRIPT = r"""
const fs = require("fs");
const { execFileSync } = require("child_process");

const cfg = JSON.parse(fs.readFileSync(0, "utf8"));
const baseDir = cfg.baseDir || "/root/.t3";
const runtimePath = `${baseDir}/userdata/server-runtime.json`;
const runtime = JSON.parse(fs.readFileSync(runtimePath, "utf8"));
const origin = runtime.origin || `http://127.0.0.1:${runtime.port || 3775}`;

function issueToken(subject) {
  const args = ["auth", "session", "issue", "--base-dir", baseDir, "--ttl", "2m", "--token-only"];
  if (subject) args.push("--subject", subject);
  return execFileSync("t3", args, { encoding: "utf8" }).trim();
}

function parseMcpBody(text) {
  for (const line of String(text || "").split(/\r?\n/)) {
    const payload = line.startsWith("data:") ? line.slice(5).trim() : line.trim();
    if (!payload || !payload.startsWith("{")) continue;
    const parsed = JSON.parse(payload);
    if (parsed.result || parsed.error) return parsed;
  }
  return null;
}

function extractResultPayload(msg) {
  if (!msg) throw new Error("Empty MCP response");
  if (msg.error) throw new Error(msg.error.message || JSON.stringify(msg.error));
  const res = msg.result || {};
  if (res.isError) {
    const errText = (res.content || []).map((c) => c.text || "").join(" ").trim();
    throw new Error(errText || "MCP tool returned error");
  }
  if (res.structuredContent) return res.structuredContent;
  for (const item of res.content || []) {
    if (item && typeof item.text === "string" && item.text.trim().startsWith("{")) {
      return JSON.parse(item.text);
    }
  }
  return res;
}

async function callMcp(mcpUrl, headers, id, name, args) {
  const res = await fetch(mcpUrl, {
    method: "POST",
    headers,
    body: JSON.stringify({ jsonrpc: "2.0", id, method: "tools/call", params: { name, arguments: args } }),
  });
  const text = await res.text();
  return extractResultPayload(parseMcpBody(text));
}

async function resolveProjectId(mcpUrl, headers, appDir, existingProjectId) {
  if (existingProjectId) return existingProjectId;
  let cursor = 0;
  let seq = 2;
  while (cursor !== null) {
    const structured = await callMcp(mcpUrl, headers, seq++, "t3_project_list", { cursor, limit: 100 });
    const projects = structured.projects || [];
    const match = projects.find((p) => p.workspaceRoot === appDir);
    if (match) return match.id;
    cursor = structured.nextCursor ?? null;
  }
  throw new Error(`Project not found in T3 for ${appDir}`);
}

function readWorktreeFromShow(threadId) {
  try {
    const raw = execFileSync(
      "t3",
      ["thread", "show", threadId, "--base-dir", baseDir, "--messages", "0", "--json"],
      { encoding: "utf8" },
    );
    const parsed = JSON.parse(raw || "{}");
    const wt = parsed.worktreePath || parsed.thread?.worktreePath || null;
    const br = parsed.branch || parsed.thread?.branch || null;
    return { worktreePath: wt, branch: br };
  } catch (_) {
    return { worktreePath: null, branch: null };
  }
}

async function main() {
  const mcpToken = issueToken("mcp-client");
  const mcpUrl = new URL("/mcp", origin).href;
  const headers = {
    "content-type": "application/json",
    "accept": "application/json, text/event-stream",
    "authorization": `Bearer ${mcpToken}`,
  };
  const initRes = await fetch(mcpUrl, {
    method: "POST",
    headers,
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: { protocolVersion: "2024-11-05", capabilities: {}, clientInfo: { name: "sf-worktree-launch", version: "1.0" } },
    }),
  });
  const sid = initRes.headers.get("mcp-session-id");
  if (sid) headers["mcp-session-id"] = sid;
  await fetch(mcpUrl, {
    method: "POST",
    headers,
    body: JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }),
  }).catch(() => {});

  const projectId = await resolveProjectId(mcpUrl, headers, cfg.appDir, cfg.projectId || null);
  const launchArgs = {
    projectId,
    title: cfg.title,
    toolSummary: "Launch Factory App worktree",
    workspaceStrategy: {
      type: "worktree",
      baseRef: cfg.baseRef || "HEAD",
      branch: cfg.branch,
      startFromOrigin: false,
    },
  };
  if (cfg.model) {
    launchArgs.modelSelection = {
      instanceId: cfg.instanceId,
      model: cfg.model,
      ...(cfg.thoughtLevel ? { options: { thought_level: cfg.thoughtLevel } } : {}),
    };
  }
  const launched = await callMcp(mcpUrl, headers, 100, "t3_thread_launch", launchArgs);
  const threadId = launched.threadId;
  if (!threadId) throw new Error("t3_thread_launch returned no threadId");
  const resolvedProjectId = launched.projectId || projectId;

  const deadline = Date.now() + (cfg.waitWorktreeSecs || 45) * 1000;
  let seq = 101;
  while (Date.now() < deadline) {
    let wtPath = null;
    let br = null;
    try {
      const readRes = await callMcp(mcpUrl, headers, seq++, "t3_thread_read", { threadId, limit: 1 });
      wtPath = readRes.worktreePath || readRes.thread?.worktreePath || null;
      br = readRes.branch || readRes.thread?.branch || null;
    } catch (_) {}
    if (!wtPath) {
      const showRes = readWorktreeFromShow(threadId);
      wtPath = showRes.worktreePath;
      br = br || showRes.branch;
    }
    if (wtPath && fs.existsSync(wtPath)) {
      process.stdout.write(JSON.stringify({ threadId, projectId: resolvedProjectId, worktreePath: wtPath, branch: br || cfg.branch }));
      return;
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  throw new Error(`Timed out waiting for T3 worktree directory for thread ${threadId}`);
}

main().catch((err) => {
  process.stderr.write((err && err.stack ? err.stack : String(err)) + "\n");
  process.exit(1);
});
"""


def resolve_worktree_base_ref(sb: Any, base_dir: str, requested_branch: str | None) -> str:
    """Resolves the Git baseRef in base_dir for creating a conversation worktree."""
    branch = (requested_branch or "").strip()
    if branch:
        rc, out, _ = exec_in_sandbox(
            sb,
            "sh",
            "-lc",
            (
                "if git -C \"$1\" show-ref --verify --quiet \"refs/remotes/origin/$2\"; then "
                "printf 'origin/%s' \"$2\"; else printf '%s' \"$2\"; fi"
            ),
            "_",
            base_dir,
            branch,
            timeout=15,
        )
        resolved = out.strip() if rc == 0 else ""
        return resolved or branch

    rc, out, _ = exec_in_sandbox(
        sb,
        "git",
        "-C",
        base_dir,
        "symbolic-ref",
        "--short",
        "HEAD",
        timeout=15,
    )
    head_branch = out.strip() if rc == 0 else ""
    if not head_branch:
        return "HEAD"
    rc_origin, _, _ = exec_in_sandbox(
        sb,
        "git",
        "-C",
        base_dir,
        "show-ref",
        "--verify",
        "--quiet",
        f"refs/remotes/origin/{head_branch}",
        timeout=15,
    )
    return f"origin/{head_branch}" if rc_origin == 0 else head_branch


def _poll_thread_worktree_path(sb: Any, thread_id: str, timeout_secs: float = 45.0) -> tuple[str | None, str | None]:
    deadline = time.monotonic() + timeout_secs
    consecutive_errors = 0
    while time.monotonic() < deadline:
        rc, out, _ = exec_in_sandbox(
            sb,
            "t3",
            "thread",
            "show",
            thread_id,
            "--base-dir",
            "/root/.t3",
            "--messages",
            "0",
            "--json",
            timeout=15,
        )
        if rc == 0 and out.strip():
            consecutive_errors = 0
            try:
                parsed = json.loads(out)
                wt = parsed.get("worktreePath") or (parsed.get("thread") or {}).get("worktreePath")
                br = parsed.get("branch") or (parsed.get("thread") or {}).get("branch")
                if wt:
                    return str(wt), str(br) if br else None
            except json.JSONDecodeError:
                pass
        else:
            consecutive_errors += 1
            if consecutive_errors >= 2:
                break
        time.sleep(0.4)
    return None, None


def start_worktree_thread_for_repo(
    sb: Any,
    app: FactoryAppRecord,
    base_dir: str,
    *,
    added_project_id: str | None,
    existing_threads: list[dict[str, Any]],
    instance_id: str,
    model: str,
    thought_level: str | None,
    log_cb: Callable[[str], None] | None = None,
) -> tuple[str, str | None, str, str]:
    """Creates a per-conversation T3 git worktree thread, installs deps if web_app, then sends prompt."""
    target_branch = app.worktree_branch or derive_worktree_branch(app.slug, app.app_id)
    for item in existing_threads:
        matches_thread = bool(app.thread_id and item.get("threadId") == app.thread_id)
        matches_branch = bool(item.get("branch") == target_branch and item.get("threadId"))
        if matches_thread or matches_branch:
            wt_path = str(item.get("worktreePath") or app.workspace_path or base_dir)
            return str(item["threadId"]), item.get("projectId") or added_project_id, wt_path, target_branch

    base_ref = resolve_worktree_base_ref(sb, base_dir, app.branch)
    payload = json.dumps(
        {
            "baseDir": "/root/.t3",
            "appDir": base_dir,
            "projectId": added_project_id,
            "title": app.title,
            "baseRef": base_ref,
            "branch": target_branch,
            "instanceId": instance_id,
            "model": model,
            "thoughtLevel": thought_level,
            "waitWorktreeSecs": 45,
        }
    )
    rc, out, err = exec_in_sandbox(
        sb, "node", "-e", _MCP_WORKTREE_LAUNCH_NODE_SCRIPT, stdin_text=payload, timeout=75
    )
    if rc == 0 and out.strip():
        launched = json.loads(out)
        thread_id = str(launched.get("threadId") or "")
        project_id = launched.get("projectId") or added_project_id
        worktree_path = str(launched.get("worktreePath") or "")
        actual_branch = str(launched.get("branch") or target_branch)
        if not thread_id or not worktree_path:
            raise RuntimeError("T3 worktree launch did not return threadId and worktreePath.")
        if app.web_app:
            if log_cb:
                log_cb(f"📦 Installing dependencies in {worktree_path}...")
            install_repo_dependencies_in_sandbox(sb, worktree_path)
        full_prompt = build_initial_thread_prompt(
            app.prompt,
            template=app.template,
            app_dir=worktree_path,
            dev_port=app.dev_port,
            web_app=app.web_app,
            repo=app.repo,
        )
        if full_prompt.strip():
            send_rc, send_out, send_err = exec_in_sandbox(
                sb,
                "t3",
                "thread",
                "send",
                thread_id,
                "-",
                "--base-dir",
                "/root/.t3",
                "--json",
                stdin_text=full_prompt,
                timeout=60,
            )
            if send_rc != 0:
                raise RuntimeError(f"t3 thread send failed for {thread_id}: {send_err or send_out}")
        return thread_id, project_id, worktree_path, actual_branch

    logger.warning("T3 MCP idle worktree launch failed for %s (%s); falling back to CLI thread start", base_dir, err or out)
    cmd = [
        "t3", "thread", "start", base_dir, "-",
        "--base-dir", "/root/.t3",
        "--provider", instance_id,
        "--model", model,
        "--worktree", base_ref,
        "--branch", target_branch,
    ]
    if thought_level:
        cmd.extend(["--option", f"thought_level={thought_level}"])
    cmd.extend(["--title", app.title, "--json"])
    prompt_text = build_initial_thread_prompt(
        app.prompt,
        template=app.template,
        app_dir=base_dir,
        dev_port=app.dev_port,
        web_app=app.web_app,
        repo=app.repo,
    )
    if not prompt_text:
        prompt_text = GENERIC_REPO_OPEN_PROMPT
    cli_rc, cli_out, cli_err = exec_in_sandbox(sb, *cmd, stdin_text=prompt_text, timeout=60)
    if cli_rc != 0:
        raise RuntimeError(f"t3 thread start --worktree failed: {cli_err or cli_out}")
    started = json.loads(cli_out)
    thread_id = str(started.get("threadId") or "")
    if not thread_id:
        raise RuntimeError("t3 thread start --worktree did not return a threadId.")
    project_id = started.get("projectId") or (started.get("projection") or {}).get("projectId") or added_project_id
    wt_path = str(started.get("worktreePath") or (started.get("thread") or {}).get("worktreePath") or "")
    if not wt_path:
        polled_wt, polled_br = _poll_thread_worktree_path(sb, thread_id, timeout_secs=20.0)
        wt_path = polled_wt or base_dir
        target_branch = polled_br or target_branch
    if app.web_app:
        if log_cb:
            log_cb(f"📦 Installing dependencies in {wt_path}...")
        install_repo_dependencies_in_sandbox(sb, wt_path)
    return thread_id, project_id, wt_path, target_branch
