import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

import {
  type AgentRole,
  ROLE_ALLOWED_TOOLS,
  LeastPrivilegeViolationError,
  assertRoleToolPrivileges,
  createRoleTools,
  createGitDiffTool,
  resolveExaApiKey,
  resolveContext7ApiKey,
  createExaWebSearchTool,
  createContext7DocsTool,
} from "./tools.ts";

const pExecFile = promisify(execFile);

test("ROLE_ALLOWED_TOOLS defines correct capabilities per role", () => {
  assert.deepEqual(ROLE_ALLOWED_TOOLS.planner, [
    "read",
    "grep",
    "find",
    "ls",
    "web_search",
    "docs_search",
  ]);
  assert.deepEqual(ROLE_ALLOWED_TOOLS.coder, [
    "read",
    "write",
    "edit",
    "bash",
    "diff",
    "web_search",
    "docs_search",
  ]);
  assert.deepEqual(ROLE_ALLOWED_TOOLS.reviewer, ["read", "grep", "find", "ls", "diff"]);
});

test("assertRoleToolPrivileges: passes for valid tool subsets", () => {
  assert.doesNotThrow(() => {
    assertRoleToolPrivileges("planner", ["read", "grep", "web_search", "docs_search"]);
    assertRoleToolPrivileges("coder", [
      "read",
      "write",
      "edit",
      "bash",
      "diff",
      "web_search",
      "docs_search",
    ]);
    assertRoleToolPrivileges("reviewer", ["read", "diff"]);
  });
});

test("assertRoleToolPrivileges: rejects search tools on Reviewer", () => {
  for (const unauthorized of ["web_search", "docs_search"]) {
    assert.throws(
      () => assertRoleToolPrivileges("reviewer", ["read", unauthorized]),
      (err) => err instanceof LeastPrivilegeViolationError && err.message.includes(unauthorized),
      `Reviewer should reject unauthorized tool: ${unauthorized}`
    );
  }
});

test("assertRoleToolPrivileges: rejects write/edit/bash tools on Planner", () => {
  for (const forbidden of ["write", "edit", "bash"]) {
    assert.throws(
      () => assertRoleToolPrivileges("planner", ["read", forbidden]),
      (err) => err instanceof LeastPrivilegeViolationError && err.message.includes(forbidden),
      `Planner should reject forbidden tool: ${forbidden}`
    );
  }
});

test("assertRoleToolPrivileges: rejects write/edit/bash tools on Reviewer", () => {
  for (const forbidden of ["write", "edit", "bash"]) {
    assert.throws(
      () => assertRoleToolPrivileges("reviewer", ["read", forbidden]),
      (err) => err instanceof LeastPrivilegeViolationError && err.message.includes(forbidden),
      `Reviewer should reject forbidden tool: ${forbidden}`
    );
  }
});

test("createRoleTools: instantiates strictly read-only tools including web_search and docs_search for Planner", async () => {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "tools-test-"));
  try {
    const tools = createRoleTools("planner", tmpDir);
    const toolNames = tools.map((t) => t.name).sort();
    assert.deepEqual(toolNames, ["docs_search", "find", "grep", "ls", "read", "web_search"]);

    // Ensure no mutating capabilities exist in planner tools
    assert.ok(!toolNames.includes("write"));
    assert.ok(!toolNames.includes("edit"));
    assert.ok(!toolNames.includes("bash"));
  } finally {
    await fs.rm(tmpDir, { recursive: true, force: true });
  }
});

test("createRoleTools: instantiates full edit, write, bash, diff, web_search, and docs_search for Coder", async () => {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "tools-test-"));
  try {
    const tools = createRoleTools("coder", tmpDir);
    const toolNames = tools.map((t) => t.name).sort();
    assert.deepEqual(toolNames, [
      "bash",
      "diff",
      "docs_search",
      "edit",
      "read",
      "web_search",
      "write",
    ]);
  } finally {
    await fs.rm(tmpDir, { recursive: true, force: true });
  }
});

test("createRoleTools: instantiates strictly read-only tools without search tools for Reviewer", async () => {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "tools-test-"));
  try {
    const tools = createRoleTools("reviewer", tmpDir);
    const toolNames = tools.map((t) => t.name).sort();
    assert.deepEqual(toolNames, ["diff", "find", "grep", "ls", "read"]);

    // Ensure Reviewer has NO bash, edit, write, or external search capabilities
    assert.ok(!toolNames.includes("write"));
    assert.ok(!toolNames.includes("edit"));
    assert.ok(!toolNames.includes("bash"));
    assert.ok(!toolNames.includes("web_search"));
    assert.ok(!toolNames.includes("docs_search"));
  } finally {
    await fs.rm(tmpDir, { recursive: true, force: true });
  }
});

test("createGitDiffTool: successfully inspects git diff in git repository", async () => {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "git-diff-test-"));
  try {
    await pExecFile("git", ["init"], { cwd: tmpDir });
    await pExecFile("git", ["config", "user.name", "Test User"], { cwd: tmpDir });
    await pExecFile("git", ["config", "user.email", "test@example.com"], { cwd: tmpDir });

    const fileA = path.join(tmpDir, "fileA.txt");
    await fs.writeFile(fileA, "line 1\nline 2\n");
    await pExecFile("git", ["add", "fileA.txt"], { cwd: tmpDir });
    await pExecFile("git", ["commit", "-m", "Initial commit"], { cwd: tmpDir });

    // Modify file
    await fs.writeFile(fileA, "line 1\nline 2 modified\nline 3\n");

    const diffTool = createGitDiffTool(tmpDir);
    assert.equal(diffTool.name, "diff");

    const result = await diffTool.execute("call-1", {}, new AbortController().signal);
    assert.ok(result.content.length > 0);
    const text = result.content[0].text;
    assert.ok(text.includes("+line 2 modified"), "diff should contain modified line");
    assert.ok(text.includes("+line 3"), "diff should contain added line");

    // Test rejecting flags starting with a dash
    const flagResult = await diffTool.execute(
      "call-2",
      { commit: "--output=/tmp/injected.txt" },
      new AbortController().signal
    );
    assert.ok(flagResult.content[0].text.includes("cannot start with a dash"));
  } finally {
    await fs.rm(tmpDir, { recursive: true, force: true });
  }
});

test("resolveExaApiKey and resolveContext7ApiKey: prioritize explicit options", async () => {
  const originalExa = process.env.EXA_API_KEY;
  const originalC7 = process.env.CONTEXT7_API_KEY;
  process.env.EXA_API_KEY = "env-exa-key";
  process.env.CONTEXT7_API_KEY = "env-c7-key";
  try {
    assert.equal(resolveExaApiKey({ apiKey: "explicit-exa" }), "explicit-exa");
    assert.equal(resolveContext7ApiKey({ apiKey: "explicit-c7" }), "explicit-c7");
  } finally {
    process.env.EXA_API_KEY = originalExa;
    process.env.CONTEXT7_API_KEY = originalC7;
  }
});

test("resolveExaApiKey and resolveContext7ApiKey: resolve from ambient environment variables", async () => {
  const originalExa = process.env.EXA_API_KEY;
  const originalC7 = process.env.CONTEXT7_API_KEY;
  process.env.EXA_API_KEY = "env-exa-val";
  process.env.CONTEXT7_API_KEY = "env-c7-val";
  try {
    assert.equal(resolveExaApiKey(), "env-exa-val");
    assert.equal(resolveContext7ApiKey(), "env-c7-val");
  } finally {
    process.env.EXA_API_KEY = originalExa;
    process.env.CONTEXT7_API_KEY = originalC7;
  }
});

test("resolveExaApiKey and resolveContext7ApiKey: resolve from config files", async () => {
  const originalExa = process.env.EXA_API_KEY;
  const originalC7 = process.env.CONTEXT7_API_KEY;
  delete process.env.EXA_API_KEY;
  delete process.env.CONTEXT7_API_KEY;

  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "api-keys-test-"));
  const envFile = path.join(tmpDir, "opencode.env");
  await fs.writeFile(
    envFile,
    `# Comment line
EXA_API_KEY="file-exa-key"
CONTEXT7_API_KEY='file-c7-key'
`
  );

  try {
    assert.equal(resolveExaApiKey({ envPath: envFile }), "file-exa-key");
    assert.equal(resolveContext7ApiKey({ envPath: envFile }), "file-c7-key");
  } finally {
    await fs.rm(tmpDir, { recursive: true, force: true });
    process.env.EXA_API_KEY = originalExa;
    process.env.CONTEXT7_API_KEY = originalC7;
  }
});

test("resolveExaApiKey and resolveContext7ApiKey: return undefined when key is missing", async () => {
  const originalExa = process.env.EXA_API_KEY;
  const originalC7 = process.env.CONTEXT7_API_KEY;
  delete process.env.EXA_API_KEY;
  delete process.env.CONTEXT7_API_KEY;

  try {
    assert.equal(resolveExaApiKey({ envPath: "/nonexistent/path.env", configFiles: [] }), undefined);
    assert.equal(resolveContext7ApiKey({ envPath: "/nonexistent/path.env", configFiles: [] }), undefined);
  } finally {
    process.env.EXA_API_KEY = originalExa;
    process.env.CONTEXT7_API_KEY = originalC7;
  }
});

test("createExaWebSearchTool: returns error when EXA_API_KEY is not configured", async () => {
  const original = process.env.EXA_API_KEY;
  delete process.env.EXA_API_KEY;
  try {
    const tool = createExaWebSearchTool({ apiKey: undefined, configFiles: [] });
    assert.equal(tool.name, "web_search");
    const result = await tool.execute("call-1", { query: "tanstack start" });
    assert.equal(result.content.length, 1);
    assert.ok(result.content[0].text.includes("Exa API key not found"));
  } finally {
    process.env.EXA_API_KEY = original;
  }
});

test("createExaWebSearchTool: returns error when query is empty", async () => {
  const tool = createExaWebSearchTool({ apiKey: "test-key" });
  const result = await tool.execute("call-2", { query: "   " });
  assert.ok(result.content[0].text.includes("Search query cannot be empty"));
});

test("createExaWebSearchTool: performs search and formats markdown output with title, url, author, and text", async () => {
  let capturedUrl = "";
  let capturedHeaders: Record<string, string> = {};
  let capturedBody: any = null;

  const mockFetch: typeof fetch = async (input, init) => {
    capturedUrl = input.toString();
    capturedHeaders = (init?.headers as Record<string, string>) || {};
    capturedBody = JSON.parse(init?.body as string);

    return new Response(
      JSON.stringify({
        results: [
          {
            title: "TanStack Start Guide",
            url: "https://tanstack.com/start",
            author: "Tanner Linsley",
            text: "TanStack Start is a full-stack React framework powered by TanStack Router.",
          },
        ],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  };

  const tool = createExaWebSearchTool({ apiKey: "test-exa-key", fetchFn: mockFetch });
  const result = await tool.execute("call-3", { query: "tanstack start guide" });

  assert.equal(capturedUrl, "https://api.exa.ai/search");
  assert.equal(capturedHeaders["x-api-key"], "test-exa-key");
  assert.equal(capturedHeaders["Authorization"], "Bearer test-exa-key");
  assert.equal(capturedBody.query, "tanstack start guide");
  assert.equal(capturedBody.numResults, 3);
  assert.equal(capturedBody.contents.text.maxCharacters, 1000);

  const text = result.content[0].text;
  assert.ok(text.includes("[TanStack Start Guide](https://tanstack.com/start)"));
  assert.ok(text.includes("**URL:** https://tanstack.com/start"));
  assert.ok(text.includes("**Author:** Tanner Linsley"));
  assert.ok(text.includes("TanStack Start is a full-stack React framework"));
});

test("createExaWebSearchTool: clamps numResults between 1 and 5", async () => {
  let capturedBody: any = null;
  const mockFetch: typeof fetch = async (_input, init) => {
    capturedBody = JSON.parse(init?.body as string);
    return new Response(JSON.stringify({ results: [] }), { status: 200 });
  };

  const tool = createExaWebSearchTool({ apiKey: "test-key", fetchFn: mockFetch });
  // Test lower clamp
  await tool.execute("call-low", { query: "test", numResults: 0 });
  assert.equal(capturedBody.numResults, 1);

  // Test upper clamp
  await tool.execute("call-high", { query: "test", numResults: 10 });
  assert.equal(capturedBody.numResults, 5);
});

test("createExaWebSearchTool: handles HTTP errors and network errors gracefully", async () => {
  // Test HTTP 401
  const httpErrTool = createExaWebSearchTool({
    apiKey: "bad-key",
    fetchFn: async () => new Response("Unauthorized", { status: 401, statusText: "Unauthorized" }),
  });
  const httpResult = await httpErrTool.execute("call-401", { query: "test query" });
  assert.ok(httpResult.content[0].text.includes("HTTP 401"));

  // Test network throw
  const netErrTool = createExaWebSearchTool({
    apiKey: "key",
    fetchFn: async () => {
      throw new Error("Connection refused");
    },
  });
  const netResult = await netErrTool.execute("call-net", { query: "test query" });
  assert.ok(netResult.content[0].text.includes("Connection refused"));
});

test("createContext7DocsTool: returns error when CONTEXT7_API_KEY is not configured", async () => {
  const original = process.env.CONTEXT7_API_KEY;
  delete process.env.CONTEXT7_API_KEY;
  try {
    const tool = createContext7DocsTool({ apiKey: undefined, configFiles: [] });
    assert.equal(tool.name, "docs_search");
    const result = await tool.execute("call-c7-missing", { query: "useQuery" });
    assert.ok(result.content[0].text.includes("Context7 API key not found"));
  } finally {
    process.env.CONTEXT7_API_KEY = original;
  }
});

test("createContext7DocsTool: returns error when query is empty", async () => {
  const tool = createContext7DocsTool({ apiKey: "test-c7-key" });
  const result = await tool.execute("call-c7-empty", { query: "   " });
  assert.ok(result.content[0].text.includes("Search query cannot be empty"));
});

test("createContext7DocsTool: queries Context7 API with query params and formats markdown with code blocks", async () => {
  let capturedUrl = "";
  let capturedHeaders: Record<string, string> = {};

  const mockFetch: typeof fetch = async (input, init) => {
    capturedUrl = input.toString();
    capturedHeaders = (init?.headers as Record<string, string>) || {};

    return new Response(
      JSON.stringify({
        codeSnippets: [
          {
            codeTitle: "Fetch data with useQuery",
            codeDescription: "Demonstrates using TanStack Query useQuery hook.",
            codeLanguage: "typescript",
            codeId: "https://tanstack.com/query/docs/use-query#example",
            codeList: [
              {
                language: "typescript",
                code: "const { data, isLoading } = useQuery({ queryKey: ['todos'], queryFn: fetchTodos });",
              },
            ],
          },
        ],
        infoSnippets: [
          {
            breadcrumb: "TanStack Query > Guides",
            content: "Queries must specify unique query keys.",
          },
        ],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  };

  const tool = createContext7DocsTool({ apiKey: "test-c7-key", fetchFn: mockFetch });
  const result = await tool.execute("call-c7-success", {
    query: "useQuery example",
    library: "TanStack Query",
    language: "TypeScript",
  });

  const parsedUrl = new URL(capturedUrl);
  assert.equal(parsedUrl.origin + parsedUrl.pathname, "https://context7.com/api/v3/search");
  assert.equal(parsedUrl.searchParams.get("query"), "useQuery example");
  assert.equal(parsedUrl.searchParams.get("library"), "TanStack Query");
  assert.equal(parsedUrl.searchParams.get("language"), "TypeScript");
  assert.equal(parsedUrl.searchParams.get("type"), "json");
  assert.equal(capturedHeaders["Authorization"], "Bearer test-c7-key");

  const text = result.content[0].text;
  assert.ok(text.includes("### Fetch data with useQuery"));
  assert.ok(text.includes("Demonstrates using TanStack Query useQuery hook."));
  assert.ok(text.includes("**Source:** https://tanstack.com/query/docs/use-query#example"));
  assert.ok(text.includes("```typescript\nconst { data, isLoading } = useQuery"));
  assert.ok(text.includes("Queries must specify unique query keys."));
});

test("createContext7DocsTool: handles HTTP errors and network errors gracefully", async () => {
  const httpErrTool = createContext7DocsTool({
    apiKey: "bad-key",
    fetchFn: async () => new Response("Forbidden", { status: 403, statusText: "Forbidden" }),
  });
  const httpResult = await httpErrTool.execute("call-c7-403", { query: "react hooks" });
  assert.ok(httpResult.content[0].text.includes("HTTP 403"));

  const netErrTool = createContext7DocsTool({
    apiKey: "key",
    fetchFn: async () => {
      throw new Error("DNS resolution failed");
    },
  });
  const netResult = await netErrTool.execute("call-c7-net", { query: "react hooks" });
  assert.ok(netResult.content[0].text.includes("DNS resolution failed"));
});

function restoreEnv(key: string, val?: string) {
  if (val === undefined) delete process.env[key];
  else process.env[key] = val;
}

test("resolveExaApiKey: parses keys with export prefix in env files", async () => {
  const originalExa = process.env.EXA_API_KEY;
  const originalC7 = process.env.CONTEXT7_API_KEY;
  delete process.env.EXA_API_KEY;
  delete process.env.CONTEXT7_API_KEY;

  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "export-env-"));
  const envFile = path.join(tmpDir, "opencode.env");
  await fs.writeFile(
    envFile,
    "export EXA_API_KEY=exported-exa-key\nexport CONTEXT7_API_KEY=exported-c7-key\n"
  );
  try {
    assert.equal(resolveExaApiKey({ envPath: envFile }), "exported-exa-key");
    assert.equal(resolveContext7ApiKey({ envPath: envFile }), "exported-c7-key");
  } finally {
    await fs.rm(tmpDir, { recursive: true, force: true });
    restoreEnv("EXA_API_KEY", originalExa);
    restoreEnv("CONTEXT7_API_KEY", originalC7);
  }
});

test("createExaWebSearchTool and createContext7DocsTool: handle abort signal gracefully", async () => {
  const abortedController = new AbortController();
  abortedController.abort();

  const exaTool = createExaWebSearchTool({
    apiKey: "key",
    fetchFn: async () => {
      throw new Error("The operation was aborted");
    },
  });
  const exaRes = await exaTool.execute("call-abort", { query: "query" }, abortedController.signal);
  assert.ok(exaRes.content[0].text.includes("aborted"));

  const c7Tool = createContext7DocsTool({
    apiKey: "key",
    fetchFn: async () => {
      throw new Error("The operation was aborted");
    },
  });
  const c7Res = await c7Tool.execute("call-abort-c7", { query: "query" }, abortedController.signal);
  assert.ok(c7Res.content[0].text.includes("aborted"));
});


