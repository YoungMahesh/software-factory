import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import { execSync } from "node:child_process";
import {
  ensureFeatureBranch,
  commitAndPushFeatureBranch,
  commitFailureDiagnostics,
} from "./git.ts";

function initTestRepo(): string {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "sf-git-test-"));
  execSync("git init -b main", { cwd: tmpDir, stdio: "ignore" });
  execSync('git config user.name "Test User"', { cwd: tmpDir, stdio: "ignore" });
  execSync('git config user.email "test@example.com"', { cwd: tmpDir, stdio: "ignore" });

  fs.writeFileSync(path.join(tmpDir, "README.md"), "# Test Repo\n", "utf-8");
  execSync("git add README.md && git commit -m 'initial commit'", {
    cwd: tmpDir,
    stdio: "ignore",
  });
  return tmpDir;
}

test("ensureFeatureBranch: creates and checks out factory/<feature> branch from current branch", () => {
  const repoDir = initTestRepo();
  try {
    const branch = ensureFeatureBranch({
      workspaceDir: repoDir,
      featureSlug: "login-flow",
    });

    assert.equal(branch, "factory/login-flow");
    const currentBranch = execSync("git branch --show-current", {
      cwd: repoDir,
      encoding: "utf-8",
    }).trim();
    assert.equal(currentBranch, "factory/login-flow");

    // Calling again is idempotent
    const branch2 = ensureFeatureBranch({
      workspaceDir: repoDir,
      featureSlug: "login-flow",
    });
    assert.equal(branch2, "factory/login-flow");
  } finally {
    fs.rmSync(repoDir, { recursive: true, force: true });
  }
});

test("commitAndPushFeatureBranch: commits changes to feature branch with structured message", () => {
  const repoDir = initTestRepo();
  try {
    ensureFeatureBranch({
      workspaceDir: repoDir,
      featureSlug: "cart-service",
    });

    // Make changes
    fs.writeFileSync(path.join(repoDir, "cart.ts"), "export const cart = [];\n", "utf-8");

    const result = commitAndPushFeatureBranch({
      workspaceDir: repoDir,
      featureSlug: "cart-service",
      ticketId: "01",
      ticketTitle: "Initialize Cart",
      push: false,
    });

    assert.equal(result.branch, "factory/cart-service");
    assert.ok(result.commitSha.length >= 7);
    assert.equal(result.pushed, false);

    const log = execSync("git log -n 1 --pretty=%B", {
      cwd: repoDir,
      encoding: "utf-8",
    }).trim();
    assert.ok(log.includes("01"));
    assert.ok(log.includes("Initialize Cart"));
  } finally {
    fs.rmSync(repoDir, { recursive: true, force: true });
  }
});

test("commitFailureDiagnostics: commits failure diagnostics to feature branch", () => {
  const repoDir = initTestRepo();
  try {
    ensureFeatureBranch({
      workspaceDir: repoDir,
      featureSlug: "payment-api",
    });

    const ticketPath = path.join(repoDir, "02-ticket.md");
    fs.writeFileSync(ticketPath, "# Ticket\n\nStatus: ready-for-human\n", "utf-8");

    const result = commitFailureDiagnostics({
      workspaceDir: repoDir,
      featureSlug: "payment-api",
      ticketId: "02",
      ticketFilePath: ticketPath,
      push: false,
    });

    assert.equal(result.branch, "factory/payment-api");
    assert.ok(result.commitSha.length >= 7);

    const log = execSync("git log -n 1 --pretty=%B", {
      cwd: repoDir,
      encoding: "utf-8",
    }).trim();
    assert.ok(log.includes("02"));
    assert.ok(log.includes("ready-for-human"));
  } finally {
    fs.rmSync(repoDir, { recursive: true, force: true });
  }
});

test("commitAndPushFeatureBranch: pushes to remote repository when remote exists", () => {
  const bareDir = fs.mkdtempSync(path.join(os.tmpdir(), "sf-git-bare-"));
  execSync("git init --bare", { cwd: bareDir, stdio: "ignore" });

  const repoDir = initTestRepo();
  try {
    execSync(`git remote add origin "${bareDir}"`, { cwd: repoDir, stdio: "ignore" });

    ensureFeatureBranch({
      workspaceDir: repoDir,
      featureSlug: "remote-test",
    });

    fs.writeFileSync(path.join(repoDir, "file.txt"), "hello", "utf-8");

    const result = commitAndPushFeatureBranch({
      workspaceDir: repoDir,
      featureSlug: "remote-test",
      ticketId: "01",
      ticketTitle: "Push Test",
      push: true,
    });

    assert.equal(result.pushed, true);

    const remoteBranches = execSync("git branch -a", {
      cwd: bareDir,
      encoding: "utf-8",
    });
    assert.ok(remoteBranches.includes("factory/remote-test"));
  } finally {
    fs.rmSync(bareDir, { recursive: true, force: true });
    fs.rmSync(repoDir, { recursive: true, force: true });
  }
});

test("commitAndPushFeatureBranch: formats commit message with Fixes #<id> on custom branch", () => {
  const repoDir = initTestRepo();
  try {
    const branch = ensureFeatureBranch({
      workspaceDir: repoDir,
      branch: "factory/issue-42",
    });
    assert.equal(branch, "factory/issue-42");

    fs.writeFileSync(path.join(repoDir, "fix.ts"), "fix content\n", "utf-8");

    const result = commitAndPushFeatureBranch({
      workspaceDir: repoDir,
      branch: "factory/issue-42",
      ticketId: "42",
      ticketTitle: "Fix race condition",
      push: false,
    });

    assert.equal(result.branch, "factory/issue-42");
    const log = execSync("git log -n 1 --pretty=%B", {
      cwd: repoDir,
      encoding: "utf-8",
    }).trim();
    assert.ok(log.includes("Fixes #42"));
    assert.ok(log.includes("resolve #42 - Fix race condition"));
  } finally {
    fs.rmSync(repoDir, { recursive: true, force: true });
  }
});
