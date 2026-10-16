import test from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";

import {
  validatePreflight,
  validatePreflightAsync,
  assertPreflight,
  assertPreflightAsync,
  parseTicket,
  parseTickets,
  getFrontierTickets,
  getNextFrontierTicket,
  PreflightError,
} from "./preflight.ts";
import { GitHubClient } from "./github.ts";
import { GitHubIssueTracker } from "./tracker/github-tracker.ts";


function createTempRepo(): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), "sf-test-repo-"));
}

function cleanupTempRepo(dir: string): void {
  fs.rmSync(dir, { recursive: true, force: true });
}

function addValidAdr(repoDir: string): void {
  const adrDir = path.join(repoDir, "docs", "adr");
  fs.mkdirSync(adrDir, { recursive: true });
  fs.writeFileSync(
    path.join(adrDir, "0001-init.md"),
    "# 0001: Architecture\n\n**Status**: Accepted\n"
  );
}


test("GitHub Pre-flight: fails when CONTEXT.md / GLOSSARY.md is missing", async () => {
  const repo = createTempRepo();
  try {
    const client = new GitHubClient({
      token: "mock-token",
      owner: "org",
      repo: "repo",
      fetch: async () => new Response("[]", { status: 200 }),
    });
    const tracker = new GitHubIssueTracker({ client });

    const result = await tracker.validatePreflight(repo, "feat-auth");
    assert.strictEqual(result.valid, false);
    assert.ok(result.errors.some((e) => e.includes("Missing domain context documentation")));
  } finally {
    cleanupTempRepo(repo);
  }
});

test("GitHub Pre-flight: fails when remote milestone does not exist", async () => {
  const repo = createTempRepo();
  try {
    fs.writeFileSync(path.join(repo, "CONTEXT.md"), "# Domain Context\n");

    const client = new GitHubClient({
      token: "mock-token",
      owner: "org",
      repo: "repo",
      fetch: async (input) => {
        const url = String(input);
        if (url.includes("/milestones")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        return new Response("Not found", { status: 404 });
      },
    });
    const tracker = new GitHubIssueTracker({ client });

    const result = await tracker.validatePreflight(repo, "feat-auth");
    assert.strictEqual(result.valid, false);
    assert.ok(result.errors.some((e) => e.includes('Milestone "feat-auth" not found')));
  } finally {
    cleanupTempRepo(repo);
  }
});

test("GitHub Pre-flight: fails when remote milestone has no assigned issues", async () => {
  const repo = createTempRepo();
  try {
    fs.writeFileSync(path.join(repo, "CONTEXT.md"), "# Domain Context\n");

    const client = new GitHubClient({
      token: "mock-token",
      owner: "org",
      repo: "repo",
      fetch: async (input) => {
        const url = String(input);
        if (url.includes("/milestones")) {
          return new Response(
            JSON.stringify([{ id: 1, number: 10, title: "feat-auth", state: "open" }]),
            { status: 200 }
          );
        }
        if (url.includes("/issues?milestone=10")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        return new Response("Not found", { status: 404 });
      },
    });
    const tracker = new GitHubIssueTracker({ client });

    const result = await tracker.validatePreflight(repo, "feat-auth");
    assert.strictEqual(result.valid, false);
    assert.ok(result.errors.some((e) => e.includes("has no issues assigned")));
  } finally {
    cleanupTempRepo(repo);
  }
});

test("GitHub Pre-flight: succeeds with CONTEXT.md and valid milestone issues without .scratch/ directory", async () => {
  const repo = createTempRepo();
  try {
    // Only CONTEXT.md and docs/adr/, NO .scratch/ directory
    fs.writeFileSync(path.join(repo, "CONTEXT.md"), "# Domain Context\n");
    addValidAdr(repo);
    assert.strictEqual(fs.existsSync(path.join(repo, ".scratch")), false);

    const client = new GitHubClient({
      token: "mock-token",
      owner: "software-factory-09-test",
      repo: "target-repo",
      fetch: async (input) => {
        const url = String(input);
        if (url.includes("/milestones")) {
          return new Response(
            JSON.stringify([
              {
                id: 1,
                number: 10,
                title: "feat-auth",
                description: "Overarching spec",
                state: "open",
              },
            ]),
            { status: 200 }
          );
        }
        if (url.includes("/issues?milestone=10")) {
          return new Response(
            JSON.stringify([
              {
                id: 101,
                number: 1,
                title: "Ticket 1",
                body: "Blocked by: None",
                state: "open",
                labels: [{ name: "factory:ready" }],
              },
            ]),
            { status: 200 }
          );
        }
        return new Response("Not found", { status: 404 });
      },
    });
    const tracker = new GitHubIssueTracker({ client });

    const result = await tracker.validatePreflight(repo, "feat-auth");
    assert.strictEqual(result.valid, true);
    assert.strictEqual(result.errors.length, 0);
  } finally {
    cleanupTempRepo(repo);
  }
});

test("GitHub Pre-flight: fails when docs/adr/ is missing", async () => {
  const repo = createTempRepo();
  try {
    fs.writeFileSync(path.join(repo, "CONTEXT.md"), "# Domain Context\n");

    const client = new GitHubClient({
      token: "mock-token",
      owner: "software-factory-09-test",
      repo: "target-repo",
    });
    const tracker = new GitHubIssueTracker({ client });

    const result = await tracker.validatePreflight(repo, "feat-auth");
    assert.strictEqual(result.valid, false);
    assert.ok(result.errors.some((e) => e.includes("docs/adr/")));
  } finally {
    cleanupTempRepo(repo);
  }
});

test("loadAcceptedAdrsBundle: bundles accepted ADRs and skips non-accepted ADRs", async () => {
  const repo = createTempRepo();
  try {
    const { loadAcceptedAdrsBundle } = await import("./preflight.ts");
    const adrDir = path.join(repo, "docs", "adr");
    fs.mkdirSync(adrDir, { recursive: true });

    fs.writeFileSync(
      path.join(adrDir, "0001-active.md"),
      "# 0001: Active Architecture\n\n**Status**: Accepted\n\nDetails of 0001."
    );
    fs.writeFileSync(
      path.join(adrDir, "0002-superseded.md"),
      "# 0002: Superseded Architecture\n\n**Status**: Superseded by 0003\n\nOld details."
    );
    fs.writeFileSync(
      path.join(adrDir, "0003-default-active.md"),
      "# 0003: Default Active\n\nNo explicit status line but valid active ADR."
    );

    fs.writeFileSync(
      path.join(adrDir, "0004-draft.md"),
      "# 0004: Draft Architecture\n\n**Status**: Draft\n\nDraft details."
    );
    fs.writeFileSync(
      path.join(adrDir, "0005-withdrawn.md"),
      "# 0005: Withdrawn Architecture\n\n**Status**: Withdrawn\n\nWithdrawn details."
    );

    const bundle = loadAcceptedAdrsBundle(repo);
    assert.ok(bundle !== undefined);
    assert.ok(bundle.includes("0001-active.md"));
    assert.ok(bundle.includes("0003-default-active.md"));
    assert.ok(!bundle.includes("0002-superseded.md"), "Superseded ADR must not be bundled");
    assert.ok(!bundle.includes("0004-draft.md"), "Draft ADR must not be bundled");
    assert.ok(!bundle.includes("0005-withdrawn.md"), "Withdrawn ADR must not be bundled");
  } finally {
    cleanupTempRepo(repo);
  }
});

test("validatePreflightAsync & assertPreflightAsync: delegates to tracker and throws PreflightError on failure", async () => {
  const repo = createTempRepo();
  try {
    fs.writeFileSync(path.join(repo, "CONTEXT.md"), "# Domain Context\n");

    const client = new GitHubClient({
      token: "mock-token",
      owner: "org",
      repo: "repo",
      fetch: async () => new Response("[]", { status: 200 }), // empty milestones
    });
    const tracker = new GitHubIssueTracker({ client });

    const result = await validatePreflightAsync(repo, "missing-feature", { tracker });
    assert.strictEqual(result.valid, false);
    assert.ok(result.errors.length > 0);

    await assert.rejects(
      async () => {
        await assertPreflightAsync(repo, "missing-feature", { tracker });
      },
      (err: any) => {
        assert.ok(err instanceof PreflightError);
        assert.ok(err.errors.length > 0);
        return true;
      }
    );
  } finally {
    cleanupTempRepo(repo);
  }
});

test("GitHub Pre-flight: fails when milestone is closed", async () => {
  const repo = createTempRepo();
  try {
    fs.writeFileSync(path.join(repo, "CONTEXT.md"), "# Domain Context\n");

    const client = new GitHubClient({
      token: "mock-token",
      owner: "org",
      repo: "repo",
      fetch: async (input) => {
        const url = String(input);
        if (url.includes("/milestones")) {
          return new Response(
            JSON.stringify([{ id: 1, number: 10, title: "feat-closed", state: "closed" }]),
            { status: 200 }
          );
        }
        return new Response("Not found", { status: 404 });
      },
    });
    const tracker = new GitHubIssueTracker({ client });

    const result = await tracker.validatePreflight(repo, "feat-closed");
    assert.strictEqual(result.valid, false);
    assert.ok(result.errors.some((e) => e.includes("is closed")));
  } finally {
    cleanupTempRepo(repo);
  }
});

test("GitHub Pre-flight: validatePreflightAsync reports error when token is missing", async () => {
  const repo = createTempRepo();
  const origToken = process.env.GH_TOKEN;
  const origGithubToken = process.env.GITHUB_TOKEN;
  try {
    delete process.env.GH_TOKEN;
    delete process.env.GITHUB_TOKEN;
    fs.writeFileSync(path.join(repo, "CONTEXT.md"), "# Domain Context\n");

    const result = await validatePreflightAsync(repo, "feat-test", {
      trackerType: "github",
      owner: "org",
      repo: "repo",
    });

    assert.strictEqual(result.valid, false);
    assert.ok(result.errors.some((e) => e.includes("Missing GitHub token")));
  } finally {
    if (origToken) process.env.GH_TOKEN = origToken;
    if (origGithubToken) process.env.GITHUB_TOKEN = origGithubToken;
    cleanupTempRepo(repo);
  }
});
