"""Idle T3 thread creation via authenticated local WebSocket RPC."""

from __future__ import annotations

import json
from typing import Any

from ._workspace import exec_in_sandbox

_IDLE_THREAD_NODE_SCRIPT = r"""
const fs = require("fs");
const crypto = require("crypto");
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

async function resolveProjectId(appDir, existingProjectId) {
  if (existingProjectId) return existingProjectId;
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
      params: { protocolVersion: "2024-11-05", capabilities: {}, clientInfo: { name: "sf-idle-thread", version: "1.0" } },
    }),
  });
  const sid = initRes.headers.get("mcp-session-id");
  if (sid) headers["mcp-session-id"] = sid;
  await fetch(mcpUrl, {
    method: "POST",
    headers,
    body: JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }),
  }).catch(() => {});

  let cursor = 0;
  while (cursor !== null) {
    const res = await fetch(mcpUrl, {
      method: "POST",
      headers,
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: 2 + cursor,
        method: "tools/call",
        params: { name: "t3_project_list", arguments: { cursor, limit: 100 } },
      }),
    });
    const text = await res.text();
    let msg = null;
    for (const line of text.split(/\r?\n/)) {
      const payload = line.startsWith("data:") ? line.slice(5).trim() : line.trim();
      if (!payload || !payload.startsWith("{")) continue;
      const parsed = JSON.parse(payload);
      if (parsed.result || parsed.error) { msg = parsed; break; }
    }
    const structured = msg?.result?.structuredContent;
    const projects = structured?.projects || [];
    const match = projects.find((p) => p.workspaceRoot === appDir);
    if (match) return match.id;
    cursor = structured?.nextCursor ?? null;
  }
  throw new Error(`Project not found in T3 for ${appDir}`);
}

async function main() {
  const projectId = await resolveProjectId(cfg.appDir, cfg.projectId || null);
  const bearer = issueToken(null);
  const ticketUrl = new URL("/api/auth/websocket-ticket/rpc", origin).href;
  const ticketRes = await fetch(ticketUrl, {
    method: "POST",
    headers: { authorization: `Bearer ${bearer}` },
  });
  if (!ticketRes.ok) {
    throw new Error(`websocket-ticket failed: ${ticketRes.status}`);
  }
  const { ticket } = await ticketRes.json();
  const wsUrl = new URL("/ws", origin);
  wsUrl.protocol = wsUrl.protocol === "https:" ? "wss:" : "ws:";
  wsUrl.searchParams.set("wsTicket", ticket);
  wsUrl.searchParams.set("orchestrationProtocol", "2");

  const threadId = crypto.randomUUID();
  const commandId = crypto.randomUUID();
  const modelSelection = { instanceId: cfg.instanceId, model: cfg.model };
  if (cfg.thoughtLevel) modelSelection.options = { thought_level: cfg.thoughtLevel };

  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      try { ws.close(); } catch (_) {}
      reject(new Error("Timed out waiting for thread.create RPC response"));
    }, 15000);
    const ws = new WebSocket(wsUrl.href);
    ws.addEventListener("open", () => {
      ws.send(JSON.stringify({
        _tag: "Request",
        id: "1",
        tag: "orchestration.dispatchCommand",
        payload: {
          type: "thread.create",
          createdBy: "user",
          creationSource: "web",
          commandId,
          threadId,
          projectId,
          title: cfg.title,
          modelSelection,
          runtimeMode: "full-access",
          interactionMode: "default",
          branch: null,
          worktreePath: null,
        },
        headers: [],
      }));
    });
    ws.addEventListener("message", (evt) => {
      let decoded;
      try {
        decoded = JSON.parse(typeof evt.data === "string" ? evt.data : Buffer.from(evt.data).toString("utf8"));
      } catch (_) {
        return;
      }
      const frames = Array.isArray(decoded) ? decoded : [decoded];
      for (const frame of frames) {
        if (frame && frame._tag === "Exit" && String(frame.requestId) === "1") {
          clearTimeout(timer);
          try { ws.close(); } catch (_) {}
          if (frame.exit && frame.exit._tag === "Success") {
            resolve();
          } else {
            reject(new Error(`thread.create failed: ${JSON.stringify(frame.exit)}`));
          }
          return;
        }
      }
    });
    ws.addEventListener("error", (err) => {
      clearTimeout(timer);
      reject(new Error(err?.message || "WebSocket error"));
    });
  });

  process.stdout.write(JSON.stringify({ threadId, projectId }));
}

main().catch((err) => {
  process.stderr.write((err && err.stack ? err.stack : String(err)) + "\n");
  process.exit(1);
});
"""


def create_idle_thread_via_ws(
    sb: Any,
    *,
    app_dir: str,
    project_id: str | None,
    title: str,
    instance_id: str,
    model: str,
    thought_level: str | None,
) -> tuple[str, str | None]:
    """Creates an idle T3 thread via local WebSocket thread.create without triggering an agent turn."""
    payload = json.dumps(
        {
            "baseDir": "/root/.t3",
            "appDir": app_dir,
            "projectId": project_id,
            "title": title,
            "instanceId": instance_id,
            "model": model,
            "thoughtLevel": thought_level,
        }
    )
    rc, out, err = exec_in_sandbox(
        sb, "node", "-e", _IDLE_THREAD_NODE_SCRIPT, stdin_text=payload, timeout=30
    )
    if rc != 0:
        raise RuntimeError(err or out or "Idle thread RPC failed")
    parsed = json.loads(out)
    thread_id = parsed.get("threadId")
    if not thread_id:
        raise RuntimeError("Idle thread RPC returned no threadId")
    return str(thread_id), parsed.get("projectId") or project_id
