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

test("discoverCommands: discovers test, lint, and typecheck commands from package.json", () => {
  const dir = createTempDir();
  try {
    const pkgJson = {
      scripts: {
        test: "jest",
        lint: "eslint .",
        typecheck: "tsc --noEmit",
      },
    };
    fs.writeFileSync(path.join(dir, "package.json"), JSON.stringify(pkgJson, null, 2));

    const discovered = discoverCommands(dir);
    assert.ok(discovered.test.some((cmd) => cmd.includes("test")));
    assert.ok(discovered.lint.some((cmd) => cmd.includes("lint")));
    assert.ok(discovered.all.length >= 2);
  } finally {
    cleanupTempDir(dir);
  }
});

test("discoverCommands: ignores npm default placeholder test script", () => {
  const dir = createTempDir();
  try {
    const pkgJson = {
      scripts: {
        test: 'echo "Error: no test specified" && exit 1',
      },
    };
    fs.writeFileSync(path.join(dir, "package.json"), JSON.stringify(pkgJson, null, 2));

    const discovered = discoverCommands(dir);
    assert.strictEqual(discovered.test.length, 0);
  } finally {
    cleanupTempDir(dir);
  }
});

test("discoverCommands: discovers pytest from pyproject.toml", () => {
  const dir = createTempDir();
  try {
    fs.writeFileSync(path.join(dir, "pyproject.toml"), "[tool.pytest.ini_options]\n");

    const discovered = discoverCommands(dir);
    assert.ok(discovered.test.includes("pytest"));
  } finally {
    cleanupTempDir(dir);
  }
});

test("verifyWorkspace: automatically uses discovered commands when commands array omitted", async () => {
  const dir = createTempDir();
  try {
    const pkgJson = {
      scripts: {
        test: "echo 'discovered test ok'",
      },
    };
    fs.writeFileSync(path.join(dir, "package.json"), JSON.stringify(pkgJson, null, 2));

    const result = await verifyWorkspace({
      workspacePath: dir,
    });

    assert.strictEqual(result.passed, true);
    assert.strictEqual(result.totalCommands, 1);
    assert.ok(result.results[0].stdout.includes("discovered test ok"));
  } finally {
    cleanupTempDir(dir);
  }
});

test("verifyWorkspace: returns passed: false when explicit commands array is empty", async () => {
  const dir = createTempDir();
  try {
    const result = await verifyWorkspace({
      workspacePath: dir,
      commands: [],
    });

    assert.strictEqual(result.passed, false);
    assert.strictEqual(result.totalCommands, 0);
    assert.ok(result.summary.includes("No test or lint commands"));
  } finally {
    cleanupTempDir(dir);
  }
});

test("smoke test: discovers commands in sandbox/factory workspace and verifies command execution", async (t) => {
  const factoryDir = import.meta.dirname;
  const discovered = discoverCommands(factoryDir);

  assert.ok(discovered.test.length > 0, "Expected discovered test commands");
  assert.ok(discovered.lint.length > 0, "Expected discovered lint/typecheck commands");
  assert.ok(discovered.test.some((c) => c.includes("test")));
  assert.ok(discovered.lint.some((c) => c.includes("typecheck")));

  // Run a quick deterministic verification in factoryDir
  const result = await verifyWorkspace({
    workspacePath: factoryDir,
    commands: ["node -e 'process.exit(0)'"],
  });
  assert.strictEqual(result.passed, true);
  assert.strictEqual(result.results[0].exitCode, 0);
});

test("verifyWorkspace: emits matching tool_start and tool_result events with command, cwd, exitCode, stdout, stderr, and isError", async () => {
  const dir = createTempDir();
  const chunks: string[] = [];
  try {
    const result = await verifyWorkspace({
      workspacePath: dir,
      commands: [
        "echo 'all 5 tests passed'",
        "sh -c 'echo \"syntax error\" >&2; exit 2'",
      ],
      failFast: false,
      telemetryStream: { write: (c: string) => chunks.push(c) },
    });

    assert.strictEqual(result.passed, false);
    assert.strictEqual(result.totalCommands, 2);

    const parsed = chunks.map((c) => parseTelemetryEnvelope(c)).filter(Boolean);
    const starts = parsed.filter((e) => e?.type === "tool_start");
    const results = parsed.filter((e) => e?.type === "tool_result");

    assert.strictEqual(starts.length, 2, "Expected 2 tool_start events");
    assert.strictEqual(results.length, 2, "Expected 2 tool_result events");

    // Command 1: success
    assert.strictEqual(starts[0]?.stage, "VERIFIER");
    assert.strictEqual(starts[0]?.data.toolName, "bash");
    assert.strictEqual(starts[0]?.data.command, "echo 'all 5 tests passed'");
    assert.strictEqual(starts[0]?.data.cwd, dir);
    assert.ok(starts[0]?.data.toolCallId);

    assert.strictEqual(results[0]?.stage, "VERIFIER");
    assert.strictEqual(results[0]?.data.toolName, "bash");
    assert.strictEqual(results[0]?.data.command, "echo 'all 5 tests passed'");
    assert.strictEqual(results[0]?.data.cwd, dir);
    assert.strictEqual(results[0]?.data.exitCode, 0);
    assert.strictEqual(results[0]?.data.isError, false);
    assert.strictEqual(results[0]?.data.toolCallId, starts[0]?.data.toolCallId);
    assert.ok(results[0]?.data.stdout.includes("all 5 tests passed"));
    assert.ok(typeof results[0]?.data.durationMs === "number");

    // Command 2: failure
    assert.strictEqual(starts[1]?.stage, "VERIFIER");
    assert.strictEqual(starts[1]?.data.command, "sh -c 'echo \"syntax error\" >&2; exit 2'");
    assert.strictEqual(starts[1]?.data.cwd, dir);

    assert.strictEqual(results[1]?.stage, "VERIFIER");
    assert.strictEqual(results[1]?.data.command, "sh -c 'echo \"syntax error\" >&2; exit 2'");
    assert.strictEqual(results[1]?.data.cwd, dir);
    assert.strictEqual(results[1]?.data.exitCode, 2);
    assert.strictEqual(results[1]?.data.isError, true);
    assert.strictEqual(results[1]?.data.toolCallId, starts[1]?.data.toolCallId);
    assert.ok(results[1]?.data.stderr.includes("syntax error"));
  } finally {
    cleanupTempDir(dir);
  }
});

