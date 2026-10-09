import test from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { createIssueTracker, resolveIssueTracker } from "./factory.ts";
import { GitHubIssueTracker } from "./github-tracker.ts";
import { LocalScratchTracker } from "./local-tracker.ts";

test("createIssueTracker: returns explicit tracker based on trackerType option", () => {
  const local = createIssueTracker({ trackerType: "local" });
  assert.ok(local instanceof LocalScratchTracker);
  assert.equal(local.id, "local");

  const gh = createIssueTracker({
    trackerType: "github",
    token: "gh_tok",
    owner: "org",
    repo: "repo",
  });
  assert.ok(gh instanceof GitHubIssueTracker);
  assert.equal(gh.id, "github");
});

test("resolveIssueTracker: auto-detects tracker based on environment and workspace", () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "factory-tracker-test-"));
  const origToken = process.env.GH_TOKEN;
  const origRepo = process.env.GH_REPO;
  const origTracker = process.env.TRACKER;

  try {
    delete process.env.TRACKER;
    process.env.GH_TOKEN = "tok_test";
    process.env.GH_REPO = "org/repo";

    // Scenario A: Workspace has .scratch/ directory -> defaults to LocalScratchTracker
    fs.mkdirSync(path.join(tmpDir, ".scratch", "feature-x"), { recursive: true });
    const trackerWithScratch = resolveIssueTracker({ workspaceDir: tmpDir, featureSlug: "feature-x" });
    assert.ok(trackerWithScratch instanceof LocalScratchTracker);

    // Scenario B: Workspace has no .scratch/ directory and GH_TOKEN is present -> defaults to GitHubIssueTracker
    const tmpEmpty = fs.mkdtempSync(path.join(os.tmpdir(), "factory-empty-test-"));
    try {
      const trackerWithoutScratch = resolveIssueTracker({ workspaceDir: tmpEmpty, featureSlug: "feature-x" });
      assert.ok(trackerWithoutScratch instanceof GitHubIssueTracker);
    } finally {
      fs.rmSync(tmpEmpty, { recursive: true, force: true });
    }

    // Scenario C: TRACKER=github env var overrides workspace directory
    process.env.TRACKER = "github";
    const trackerOverride = resolveIssueTracker({ workspaceDir: tmpDir, featureSlug: "feature-x" });
    assert.ok(trackerOverride instanceof GitHubIssueTracker);
  } finally {
    process.env.GH_TOKEN = origToken;
    process.env.GH_REPO = origRepo;
    if (origTracker !== undefined) {
      process.env.TRACKER = origTracker;
    } else {
      delete process.env.TRACKER;
    }
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});
