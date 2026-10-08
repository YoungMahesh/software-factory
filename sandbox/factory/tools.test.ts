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
} from "./tools.ts";

const pExecFile = promisify(execFile);

test("ROLE_ALLOWED_TOOLS defines correct capabilities per role", () => {
  assert.deepEqual(ROLE_ALLOWED_TOOLS.planner, ["read", "grep", "find", "ls"]);
  assert.deepEqual(ROLE_ALLOWED_TOOLS.coder, ["read", "write", "edit", "bash", "diff"]);
  assert.deepEqual(ROLE_ALLOWED_TOOLS.reviewer, ["read", "grep", "find", "ls", "diff"]);
});

test("assertRoleToolPrivileges: passes for valid tool subsets", () => {
  assert.doesNotThrow(() => {
    assertRoleToolPrivileges("planner", ["read", "grep"]);
    assertRoleToolPrivileges("coder", ["read", "write", "edit", "bash", "diff"]);
    assertRoleToolPrivileges("reviewer", ["read", "diff"]);
  });
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

test("createRoleTools: instantiates strictly read-only tools for Planner", async () => {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "tools-test-"));
  try {
    const tools = createRoleTools("planner", tmpDir);
    const toolNames = tools.map((t) => t.name).sort();
    assert.deepEqual(toolNames, ["find", "grep", "ls", "read"]);

    // Ensure no mutating capabilities exist in planner tools
    assert.ok(!toolNames.includes("write"));
    assert.ok(!toolNames.includes("edit"));
    assert.ok(!toolNames.includes("bash"));
  } finally {
    await fs.rm(tmpDir, { recursive: true, force: true });
  }
});

test("createRoleTools: instantiates full edit, write, bash, and diff tools for Coder", async () => {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "tools-test-"));
  try {
    const tools = createRoleTools("coder", tmpDir);
    const toolNames = tools.map((t) => t.name).sort();
    assert.deepEqual(toolNames, ["bash", "diff", "edit", "read", "write"]);
  } finally {
    await fs.rm(tmpDir, { recursive: true, force: true });
  }
});

test("createRoleTools: instantiates strictly read-only tools including diff for Reviewer", async () => {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "tools-test-"));
  try {
    const tools = createRoleTools("reviewer", tmpDir);
    const toolNames = tools.map((t) => t.name).sort();
    assert.deepEqual(toolNames, ["diff", "find", "grep", "ls", "read"]);

    // Ensure Reviewer has NO bash, edit, or write capabilities
    assert.ok(!toolNames.includes("write"));
    assert.ok(!toolNames.includes("edit"));
    assert.ok(!toolNames.includes("bash"));
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
