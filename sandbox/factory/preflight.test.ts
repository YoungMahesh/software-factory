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

test("validatePreflight: reports error when spec.md is missing", () => {
  const repo = createTempRepo();
  try {
    // Has CONTEXT.md and AGENTS.md, but no .scratch/feat/spec.md
    fs.writeFileSync(path.join(repo, "CONTEXT.md"), "# Domain Context");
    fs.writeFileSync(path.join(repo, "AGENTS.md"), "# Agents\n\n## Agent skills\n");
    addValidAdr(repo);

    const result = validatePreflight(repo, "test-feature");
    assert.strictEqual(result.valid, false);
    assert.ok(result.errors.some((err) => err.includes(".scratch/test-feature/spec.md")));
  } finally {
    cleanupTempRepo(repo);
  }
});

test("validatePreflight: reports error when CONTEXT.md is missing", () => {
  const repo = createTempRepo();
  try {
    const featDir = path.join(repo, ".scratch", "test-feature");
    fs.mkdirSync(featDir, { recursive: true });
    fs.writeFileSync(path.join(featDir, "spec.md"), "# Spec");
    fs.writeFileSync(path.join(repo, "AGENTS.md"), "## Agent skills\n");
    addValidAdr(repo);

    const result = validatePreflight(repo, "test-feature");
    assert.strictEqual(result.valid, false);
    assert.ok(result.errors.some((err) => err.includes("CONTEXT.md")));
  } finally {
    cleanupTempRepo(repo);
  }
});

test("validatePreflight: accepts CONTEXT.md in domain path", () => {
  const repo = createTempRepo();
  try {
    const featDir = path.join(repo, ".scratch", "test-feature");
    fs.mkdirSync(featDir, { recursive: true });
    fs.writeFileSync(path.join(featDir, "spec.md"), "# Spec");
    const domainDir = path.join(repo, "src", "domain");
    fs.mkdirSync(domainDir, { recursive: true });
    fs.writeFileSync(path.join(domainDir, "CONTEXT.md"), "# Domain Context");
    fs.writeFileSync(path.join(repo, "AGENTS.md"), "## Agent skills\n");
    addValidAdr(repo);

    const result = validatePreflight(repo, "test-feature");
    assert.strictEqual(result.valid, true);
    assert.strictEqual(result.errors.length, 0);
  } finally {
    cleanupTempRepo(repo);
  }
});

test("validatePreflight: accepts GLOSSARY.md at repository root", () => {
  const repo = createTempRepo();
  try {
    const featDir = path.join(repo, ".scratch", "test-feature");
    fs.mkdirSync(featDir, { recursive: true });
    fs.writeFileSync(path.join(featDir, "spec.md"), "# Spec");
    fs.writeFileSync(path.join(repo, "GLOSSARY.md"), "# Domain Glossary");
    fs.writeFileSync(path.join(repo, "AGENTS.md"), "## Agent skills\n");
    addValidAdr(repo);

    const result = validatePreflight(repo, "test-feature");
    assert.strictEqual(result.valid, true);
    assert.strictEqual(result.errors.length, 0);
  } finally {
    cleanupTempRepo(repo);
  }
});

test("validatePreflight: accepts GLOSSARY.md in docs path", () => {
  const repo = createTempRepo();
  try {
    const featDir = path.join(repo, ".scratch", "test-feature");
    fs.mkdirSync(featDir, { recursive: true });
    fs.writeFileSync(path.join(featDir, "spec.md"), "# Spec");
    const docsDir = path.join(repo, "docs");
    fs.mkdirSync(docsDir, { recursive: true });
    fs.writeFileSync(path.join(docsDir, "GLOSSARY.md"), "# Domain Glossary");
    fs.writeFileSync(path.join(repo, "AGENTS.md"), "## Agent skills\n");
    addValidAdr(repo);

    const result = validatePreflight(repo, "test-feature");
    assert.strictEqual(result.valid, true);
    assert.strictEqual(result.errors.length, 0);
  } finally {
    cleanupTempRepo(repo);
  }
});

test("validatePreflight: reports error when issue tracking config is missing", () => {
  const repo = createTempRepo();
  try {
    const featDir = path.join(repo, ".scratch", "test-feature");
    fs.mkdirSync(featDir, { recursive: true });
    fs.writeFileSync(path.join(featDir, "spec.md"), "# Spec");
    fs.writeFileSync(path.join(repo, "CONTEXT.md"), "# Context");
    addValidAdr(repo);

    const result = validatePreflight(repo, "test-feature");
    assert.strictEqual(result.valid, false);
    assert.ok(result.errors.some((err) => err.includes("issue tracking configuration")));
  } finally {
    cleanupTempRepo(repo);
  }
});

test("validatePreflight: accepts docs/agents/issue-tracker.md as issue tracking config", () => {
  const repo = createTempRepo();
  try {
    const featDir = path.join(repo, ".scratch", "test-feature");
    fs.mkdirSync(featDir, { recursive: true });
    fs.writeFileSync(path.join(featDir, "spec.md"), "# Spec");
    fs.writeFileSync(path.join(repo, "CONTEXT.md"), "# Context");
    const docsDir = path.join(repo, "docs", "agents");
    fs.mkdirSync(docsDir, { recursive: true });
    fs.writeFileSync(path.join(docsDir, "issue-tracker.md"), "# Issue tracker");
    addValidAdr(repo);

    const result = validatePreflight(repo, "test-feature");
    assert.strictEqual(result.valid, true);
    assert.strictEqual(result.errors.length, 0);
  } finally {
    cleanupTempRepo(repo);
  }
});

test("validatePreflight: accepts CLAUDE.md with ## Agent skills", () => {
  const repo = createTempRepo();
  try {
    const featDir = path.join(repo, ".scratch", "test-feature");
    fs.mkdirSync(featDir, { recursive: true });
    fs.writeFileSync(path.join(featDir, "spec.md"), "# Spec");
    fs.writeFileSync(path.join(repo, "CONTEXT.md"), "# Context");
    fs.writeFileSync(path.join(repo, "CLAUDE.md"), "# Instructions\n\n## Agent skills\n");
    addValidAdr(repo);

    const result = validatePreflight(repo, "test-feature");
    assert.strictEqual(result.valid, true);
    assert.strictEqual(result.errors.length, 0);
  } finally {
    cleanupTempRepo(repo);
  }
});

test("validatePreflight: reports error when docs/adr directory is missing", () => {
  const repo = createTempRepo();
  try {
    const featDir = path.join(repo, ".scratch", "test-feature");
    fs.mkdirSync(featDir, { recursive: true });
    fs.writeFileSync(path.join(featDir, "spec.md"), "# Spec");
    fs.writeFileSync(path.join(repo, "CONTEXT.md"), "# Context");
    fs.writeFileSync(path.join(repo, "AGENTS.md"), "## Agent skills\n");

    const result = validatePreflight(repo, "test-feature");
    assert.strictEqual(result.valid, false);
    assert.ok(result.errors.some((err) => err.includes("docs/adr/")));
  } finally {
    cleanupTempRepo(repo);
  }
});

test("validatePreflight: reports error when docs/adr has no accepted ADRs", () => {
  const repo = createTempRepo();
  try {
    const featDir = path.join(repo, ".scratch", "test-feature");
    fs.mkdirSync(featDir, { recursive: true });
    fs.writeFileSync(path.join(featDir, "spec.md"), "# Spec");
    fs.writeFileSync(path.join(repo, "CONTEXT.md"), "# Context");
    fs.writeFileSync(path.join(repo, "AGENTS.md"), "## Agent skills\n");

    const adrDir = path.join(repo, "docs", "adr");
    fs.mkdirSync(adrDir, { recursive: true });
    fs.writeFileSync(
      path.join(adrDir, "0001-old.md"),
      "# 0001: Old Architecture\n\n**Status**: Superseded by 0002\n"
    );
    fs.writeFileSync(
      path.join(adrDir, "0002-dep.md"),
      "# 0002: Deprecated Architecture\n\n**Status**: Deprecated\n"
    );

    const result = validatePreflight(repo, "test-feature");
    assert.strictEqual(result.valid, false);
    assert.ok(result.errors.some((err) => err.includes("Missing accepted architectural decision records")));
  } finally {
    cleanupTempRepo(repo);
  }
});

test("validatePreflight: passes when docs/adr contains accepted ADR", () => {
  const repo = createTempRepo();
  try {
    const featDir = path.join(repo, ".scratch", "test-feature");
    fs.mkdirSync(featDir, { recursive: true });
    fs.writeFileSync(path.join(featDir, "spec.md"), "# Spec");
    fs.writeFileSync(path.join(repo, "CONTEXT.md"), "# Context");
    fs.writeFileSync(path.join(repo, "AGENTS.md"), "## Agent skills\n");

    const adrDir = path.join(repo, "docs", "adr");
    fs.mkdirSync(adrDir, { recursive: true });
    fs.writeFileSync(
      path.join(adrDir, "0001-active.md"),
      "# 0001: Active Architecture\n\n**Status**: Accepted\n"
    );

    const result = validatePreflight(repo, "test-feature");
    assert.strictEqual(result.valid, true);
    assert.strictEqual(result.errors.length, 0);
  } finally {
    cleanupTempRepo(repo);
  }
});

test("assertPreflight: throws actionable PreflightError when prerequisites missing", () => {
  const repo = createTempRepo();
  try {
    assert.throws(
      () => assertPreflight(repo, "test-feature"),
      (err: unknown) => {
        assert.ok(err instanceof PreflightError);
        const preflightErr = err as PreflightError;
        assert.ok(preflightErr.message.includes(".scratch/test-feature/spec.md"));
        assert.ok(preflightErr.message.includes("CONTEXT.md"));
        return true;
      }
    );
  } finally {
    cleanupTempRepo(repo);
  }
});

test("parseTicket: parses ticket headers, status, blockers", () => {
  const repo = createTempRepo();
  try {
    const ticketPath = path.join(repo, "01-sample-task.md");
    fs.writeFileSync(
      ticketPath,
      `# 01: Sample Task

**What to build:** Test task.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Item 1
`
    );

    const ticket = parseTicket(ticketPath);
    assert.strictEqual(ticket.id, "01");
    assert.strictEqual(ticket.number, 1);
    assert.strictEqual(ticket.title, "Sample Task");
    assert.strictEqual(ticket.status, "ready-for-agent");
    assert.deepStrictEqual(ticket.blockedBy, []);
  } finally {
    cleanupTempRepo(repo);
  }
});

test("parseTicket: parses multiple blockers in header", () => {
  const repo = createTempRepo();
  try {
    const ticketPath = path.join(repo, "03-third-task.md");
    fs.writeFileSync(
      ticketPath,
      `# 03: Third Task

**Blocked by:** 01: Sample Task, 02: Second Task

**Status:** ready-for-agent
`
    );

    const ticket = parseTicket(ticketPath);
    assert.strictEqual(ticket.id, "03");
    assert.strictEqual(ticket.number, 3);
    assert.strictEqual(ticket.title, "Third Task");
    assert.deepStrictEqual(ticket.blockedBy, ["01", "02"]);
  } finally {
    cleanupTempRepo(repo);
  }
});

test("parseTickets & getFrontierTickets: resolves dependencies and returns unblocked tickets in order", () => {
  const repo = createTempRepo();
  try {
    const issuesDir = path.join(repo, ".scratch", "feature-x", "issues");
    fs.mkdirSync(issuesDir, { recursive: true });

    // Ticket 01: ready-for-agent, unblocked
    fs.writeFileSync(
      path.join(issuesDir, "01-first.md"),
      "# 01: First\n\nBlocked by: None\nStatus: ready-for-agent\n"
    );

    // Ticket 02: ready-for-agent, unblocked
    fs.writeFileSync(
      path.join(issuesDir, "02-second.md"),
      "# 02: Second\n\nBlocked by: None\nStatus: ready-for-agent\n"
    );

    // Ticket 03: ready-for-agent, blocked by 01 and 02
    fs.writeFileSync(
      path.join(issuesDir, "03-third.md"),
      "# 03: Third\n\nBlocked by: 01, 02\nStatus: ready-for-agent\n"
    );

    // Ticket 04: claimed, unblocked
    fs.writeFileSync(
      path.join(issuesDir, "04-fourth.md"),
      "# 04: Fourth\n\nBlocked by: None\nStatus: claimed\n"
    );

    const tickets = parseTickets(repo, "feature-x");
    assert.strictEqual(tickets.length, 4);
    assert.strictEqual(tickets[0].id, "01");
    assert.strictEqual(tickets[1].id, "02");
    assert.strictEqual(tickets[2].id, "03");
    assert.strictEqual(tickets[3].id, "04");

    // Initially, frontier should be [01, 02]
    const frontier = getFrontierTickets(tickets);
    assert.deepStrictEqual(
      frontier.map((t) => t.id),
      ["01", "02"]
    );

    // If 01 is resolved, frontier is [02] (03 still blocked by 02)
    tickets[0].status = "resolved";
    const frontierAfter01 = getFrontierTickets(tickets);
    assert.deepStrictEqual(
      frontierAfter01.map((t) => t.id),
      ["02"]
    );

    // Test getNextFrontierTicket
    assert.strictEqual(getNextFrontierTicket(tickets)?.id, "02");

    // If 02 is also resolved, frontier is [03]
    tickets[1].status = "resolved";
    assert.strictEqual(getNextFrontierTicket(tickets)?.id, "03");

    // Test that non-ticket files like README.md are ignored
    fs.writeFileSync(path.join(issuesDir, "README.md"), "# Issues Directory\n\nThis is not a ticket.\n");
    const ticketsWithReadme = parseTickets(repo, "feature-x");
    assert.strictEqual(ticketsWithReadme.length, 4);
    assert.ok(!ticketsWithReadme.some((t) => t.id === "README"));
  } finally {
    cleanupTempRepo(repo);
  }
});

test("parseTicket: handles backticks and annotated status strings", () => {
  const repo = createTempRepo();
  try {
    const ticketPath = path.join(repo, "05-annotated.md");
    fs.writeFileSync(
      ticketPath,
      "# 05: Annotated\n\nStatus: `ready-for-agent` (ready)\nBlocked by: None\n"
    );
    const ticket = parseTicket(ticketPath);
    assert.strictEqual(ticket.status, "ready-for-agent");
  } finally {
    cleanupTempRepo(repo);
  }
});

test("smoke test: validates software-factory repo itself", (t) => {
  const repoRoot = path.resolve(import.meta.dirname, "../..");
  if (!fs.existsSync(path.join(repoRoot, ".scratch", "software-factory", "spec.md"))) {
    t.skip("Skipping smoke test: software-factory workspace root not present at " + repoRoot);
    return;
  }
  const result = validatePreflight(repoRoot, "software-factory");
  assert.strictEqual(result.valid, true, `Expected valid preflight, got errors: ${result.errors.join("; ")}`);
  assert.strictEqual(result.errors.length, 0);

  const tickets = parseTickets(repoRoot, "software-factory");
  assert.ok(tickets.length >= 6);
  assert.strictEqual(tickets[0].id, "01");
  assert.ok(tickets[0].status === "ready-for-agent" || tickets[0].status === "resolved");

  const frontier = getFrontierTickets(tickets);
  // As tickets are resolved, frontier advances to completion
  assert.ok(frontier.length === 0 || frontier.some((t) => t.id === "06"));
});

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



