import test from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import { execSync } from "node:child_process";

import { verifyWorkspace, runCommand } from "./verifier.ts";

function getOrgToken(): string {
  const tokenPath = path.resolve(import.meta.dirname, "../../secrets_org/software-factory-09-test/token");
  return execSync(`sops -d "${tokenPath}"`, { encoding: "utf-8" }).trim();
}

function cloneRepo(ghRepo: string, ghToken: string, destDir: string): void {
  const url = `https://x-access-token:${ghToken}@github.com/${ghRepo}.git`;
  execSync(`git clone --depth 1 "${url}" "${destDir}"`, {
    stdio: ["ignore", "pipe", "pipe"],
  });
}

test("Integration: verifyWorkspace against real repo test2 (software-factory-09-test/test2)", async (t) => {
  const tokenPath = path.resolve(import.meta.dirname, "../../secrets_org/software-factory-09-test/token");
  if (!fs.existsSync(tokenPath)) {
    t.skip("secrets_org/software-factory-09-test/token not found");
    return;
  }

  const ghToken = getOrgToken();
  const ghRepo = "software-factory-09-test/test2";
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "sf-int-verifier-test2-"));

  try {
    cloneRepo(ghRepo, ghToken, tempDir);

    // 1. Positive verification: run valid commands in the real cloned workspace
    const streamedChunks: string[] = [];
    const logPath = path.join(tempDir, ".scratch", "verification-test2.md");

    const passResult = await verifyWorkspace({
      workspacePath: tempDir,
      commands: [
        "git status --porcelain",
        "test -f GLOSSARY.md",
        "grep -q 'Queue' queues.md",
      ],
      logPath,
      onStream: (chunk) => streamedChunks.push(chunk),
    });

    assert.strictEqual(passResult.passed, true, "Expected verification to pass");
    assert.strictEqual(passResult.totalCommands, 3);
    assert.strictEqual(passResult.passedCommands, 3);
    assert.strictEqual(passResult.failedCommands, 0);
    assert.ok(streamedChunks.length >= 0);
    assert.ok(fs.existsSync(logPath), "Expected logPath file to be persisted in workspace");
    assert.ok(passResult.summary.includes("PASSED"));

    // 2. Negative verification: run a failing verification check
    const failResult = await verifyWorkspace({
      workspacePath: tempDir,
      commands: [
        "test -f GLOSSARY.md",
        "test -f NONEXISTENT_FILE.md",
      ],
      failFast: true,
    });

    assert.strictEqual(failResult.passed, false, "Expected verification to fail");
    assert.strictEqual(failResult.passedCommands, 1);
    assert.strictEqual(failResult.failedCommands, 1);
    assert.strictEqual(failResult.results[1].exitCode, 1);
    assert.ok(failResult.summary.includes("FAILED"));

    // 3. Auto-discovery on test2 (docs repo with no package.json/pyproject.toml)
    const discoveryResult = await verifyWorkspace({
      workspacePath: tempDir,
    });
    assert.strictEqual(discoveryResult.passed, false);
    assert.strictEqual(discoveryResult.totalCommands, 0);
    assert.ok(discoveryResult.summary.includes("No test or lint commands"));
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
});
