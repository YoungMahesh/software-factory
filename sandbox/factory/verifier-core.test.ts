import test from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";

import { runCommand, verifyWorkspace, discoverCommands } from "./verifier.ts";
import { parseTelemetryEnvelope } from "./events.ts";

function createTempDir(): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), "sf-verifier-test-"));
}

function cleanupTempDir(dir: string): void {
  fs.rmSync(dir, { recursive: true, force: true });
}

test("runCommand: executes successful command, captures exit code 0 and stdout", async () => {
  const dir = createTempDir();
  try {
    const result = await runCommand("echo 'verifier works'", { cwd: dir });
    assert.strictEqual(result.passed, true);
    assert.strictEqual(result.exitCode, 0);
    assert.strictEqual(result.signal, null);
    assert.strictEqual(result.timedOut, false);
    assert.strictEqual(result.stdout.trim(), "verifier works");
    assert.strictEqual(result.stderr, "");
    assert.ok(result.durationMs >= 0);
  } finally {
    cleanupTempDir(dir);
  }
});

test("runCommand: captures non-zero exit code and stderr deterministically", async () => {
  const dir = createTempDir();
  try {
    const result = await runCommand("sh -c 'echo \"failure log\" >&2; exit 3'", { cwd: dir });
    assert.strictEqual(result.passed, false);
    assert.strictEqual(result.exitCode, 3);
    assert.strictEqual(result.signal, null);
    assert.strictEqual(result.timedOut, false);
    assert.strictEqual(result.stderr.trim(), "failure log");
  } finally {
    cleanupTempDir(dir);
  }
});

test("runCommand: treats non-zero exit codes like 127 and 1 as failure", async () => {
  const dir = createTempDir();
  try {
    const result1 = await runCommand("sh -c 'exit 1'", { cwd: dir });
    assert.strictEqual(result1.passed, false);
    assert.strictEqual(result1.exitCode, 1);

    const result2 = await runCommand("sh -c 'exit 127'", { cwd: dir });
    assert.strictEqual(result2.passed, false);
    assert.strictEqual(result2.exitCode, 127);
  } finally {
    cleanupTempDir(dir);
  }
});

test("runCommand: streams stdout and stderr chunks during execution via onStream callback", async () => {
  const dir = createTempDir();
  try {
    const streamed: { chunk: string; stream: "stdout" | "stderr" }[] = [];
    const result = await runCommand(
      "sh -c 'echo \"out-line-1\"; echo \"err-line-1\" >&2; echo \"out-line-2\"'",
      {
        cwd: dir,
        onStream: (chunk, stream) => {
          streamed.push({ chunk, stream });
        },
      }
    );

    assert.strictEqual(result.passed, true);
    assert.ok(streamed.some((s) => s.stream === "stdout" && s.chunk.includes("out-line-1")));
    assert.ok(streamed.some((s) => s.stream === "stderr" && s.chunk.includes("err-line-1")));
    assert.ok(streamed.some((s) => s.stream === "stdout" && s.chunk.includes("out-line-2")));
    assert.ok(result.output.includes("out-line-1"));
    assert.ok(result.output.includes("err-line-1"));
  } finally {
    cleanupTempDir(dir);
  }
});

test("runCommand: handles process timeout gracefully and kills process", async () => {
  const dir = createTempDir();
  try {
    const start = Date.now();
    const result = await runCommand("sleep 10", {
      cwd: dir,
      timeoutMs: 150,
    });
    const elapsed = Date.now() - start;

    assert.strictEqual(result.passed, false);
    assert.strictEqual(result.timedOut, true);
    assert.ok(result.error?.includes("timed out") ?? false);
    assert.ok(elapsed < 2000, `Expected elapsed < 2000ms, got ${elapsed}ms`);
  } finally {
    cleanupTempDir(dir);
  }
});

test("runCommand: handles spawn / directory errors gracefully without uncaught rejection", async () => {
  const result = await runCommand("echo 'should fail'", {
    cwd: "/nonexistent/path/for/verifier/test",
  });

  assert.strictEqual(result.passed, false);
  assert.strictEqual(result.exitCode, null);
  assert.ok(result.error !== undefined);
  assert.ok(result.error?.includes("ENOENT") || result.error?.includes("spawn"));
});

test("verifyWorkspace: executes specified test and lint commands and returns passed: true when all succeed", async () => {
  const dir = createTempDir();
  try {
    const result = await verifyWorkspace({
      workspacePath: dir,
      commands: ["echo 'lint passed'", "echo 'test passed'"],
    });

    assert.strictEqual(result.passed, true);
    assert.strictEqual(result.totalCommands, 2);
    assert.strictEqual(result.passedCommands, 2);
    assert.strictEqual(result.failedCommands, 0);
    assert.strictEqual(result.results.length, 2);
    assert.strictEqual(result.results[0].passed, true);
    assert.strictEqual(result.results[0].stdout.trim(), "lint passed");
    assert.strictEqual(result.results[1].passed, true);
    assert.strictEqual(result.results[1].stdout.trim(), "test passed");
    assert.ok(result.summary.includes("lint passed") || result.summary.includes("PASSED"));
  } finally {
    cleanupTempDir(dir);
  }
});

test("verifyWorkspace: returns passed: false deterministically when any command exits non-zero", async () => {
  const dir = createTempDir();
  try {
    const result = await verifyWorkspace({
      workspacePath: dir,
      commands: ["echo 'step 1 ok'", "sh -c 'echo \"lint failed\" >&2; exit 2'"],
    });

    assert.strictEqual(result.passed, false);
    assert.strictEqual(result.passedCommands, 1);
    assert.strictEqual(result.failedCommands, 1);
    assert.strictEqual(result.results[1].passed, false);
    assert.strictEqual(result.results[1].exitCode, 2);
  } finally {
    cleanupTempDir(dir);
  }
});

test("verifyWorkspace: failFast stops on first failure by default, or continues when false", async () => {
  const dir = createTempDir();
  try {
    // Default failFast: true
    const fastResult = await verifyWorkspace({
      workspacePath: dir,
      commands: ["sh -c 'exit 1'", "echo 'should not run'"],
    });
    assert.strictEqual(fastResult.results.length, 1);
    assert.strictEqual(fastResult.failedCommands, 1);

    // failFast: false
    const continueResult = await verifyWorkspace({
      workspacePath: dir,
      commands: ["sh -c 'exit 1'", "echo 'should run'"],
      failFast: false,
    });
    assert.strictEqual(continueResult.results.length, 2);
    assert.strictEqual(continueResult.failedCommands, 1);
    assert.strictEqual(continueResult.passedCommands, 1);
    assert.strictEqual(continueResult.results[1].passed, true);
  } finally {
    cleanupTempDir(dir);
  }
});

test("verifyWorkspace: preserves both stdout and stderr in failure details", async () => {
  const dir = createTempDir();
  try {
    const result = await verifyWorkspace({
      workspacePath: dir,
      commands: ["sh -c 'echo \"AssertionError: expected true\" ; echo \"DeprecationWarning: sample\" >&2; exit 1'"],
    });

    assert.strictEqual(result.passed, false);
    assert.ok(result.summary.includes("FAILED"));
    assert.ok(result.summary.includes("| FAIL |"));
    assert.ok(result.summary.includes("AssertionError: expected true"), "Must preserve stdout test assertion");
    assert.ok(result.summary.includes("DeprecationWarning: sample"), "Must preserve stderr warning");
  } finally {
    cleanupTempDir(dir);
  }
});

test("verifyWorkspace: persists structured markdown log when logPath is provided", async () => {
  const dir = createTempDir();
  try {
    const logFile = path.join(dir, ".scratch", "verification.md");
    const result = await verifyWorkspace({
      workspacePath: dir,
      commands: ["echo 'tested'"],
      logPath: logFile,
    });

    assert.strictEqual(result.passed, true);
    assert.ok(fs.existsSync(logFile));
    const content = fs.readFileSync(logFile, "utf-8");
    assert.ok(content.includes("### Verification Summary: PASSED"));
    assert.ok(content.includes("`echo 'tested'`"));
  } finally {
    cleanupTempDir(dir);
  }
});
