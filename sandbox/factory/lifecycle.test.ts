import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import { execSync } from "node:child_process";
import { runTicketLifecycle } from "./lifecycle.ts";
import { type Ticket } from "./preflight.ts";
import { type ImplementationPlan, type ReviewVerdict } from "./harness.ts";
import { type VerificationResult } from "./verifier.ts";
import { ensureFeatureBranch } from "./git.ts";
import { GitHubClient } from "./github.ts";
import { GitHubIssueTracker } from "./tracker/github-tracker.ts";

function setupMockWorkspace(featureSlug: string, ticketNum: string = "01"): {
  repoDir: string;
  ticket: Ticket;
  specPath: string;
} {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "sf-lifecycle-test-"));
  execSync("git init -b main", { cwd: tmpDir, stdio: "ignore" });
  execSync('git config user.name "Test Runner"', { cwd: tmpDir, stdio: "ignore" });
  execSync('git config user.email "runner@example.com"', { cwd: tmpDir, stdio: "ignore" });

  fs.writeFileSync(path.join(tmpDir, "README.md"), "# Mock Repo\n", "utf-8");
  execSync("git add README.md && git commit -m 'initial commit'", {
    cwd: tmpDir,
    stdio: "ignore",
  });

  const scratchDir = path.join(tmpDir, ".scratch", featureSlug);
  const issuesDir = path.join(scratchDir, "issues");
  fs.mkdirSync(issuesDir, { recursive: true });

  const specPath = path.join(scratchDir, "spec.md");
  fs.writeFileSync(specPath, `# Spec: ${featureSlug}\n\nFeature specification.`, "utf-8");

  const ticketPath = path.join(issuesDir, `${ticketNum}-test-item.md`);
  const ticketContent = `# ${ticketNum}: Test Item

**What to build:** Implement test item.

**Blocked by:** None

**Status:** ready-for-agent

- [ ] Task 1
`;
  fs.writeFileSync(ticketPath, ticketContent, "utf-8");

  const ticket: Ticket = {
    id: ticketNum,
    number: parseInt(ticketNum, 10),
    slug: "test-item",
    title: "Test Item",
    filePath: ticketPath,
    status: "ready-for-agent",
    blockedBy: [],
  };

  return { repoDir: tmpDir, ticket, specPath };
}

const mockPlan: ImplementationPlan = {
  ticketId: "01",
  summary: "Implement mock item",
  affectedFiles: ["src/item.ts"],
  testCommands: ["echo 'test passed'"],
  steps: ["1. Add item.ts"],
  rawContent: "```json\n{}\n```",
};

const mockPassingReview: ReviewVerdict = {
  verdict: "approved",
  summary: "Changes look great",
  specCompliance: { passed: true, details: "All criteria met" },
  standardsCompliance: { passed: true, details: "Follows repo standards" },
  issues: [],
  rawContent: '{"verdict":"approved"}',
};

const mockRejectingReview: ReviewVerdict = {
  verdict: "rejected",
  summary: "Missing edge case tests",
  specCompliance: { passed: false, details: "Missing negative test" },
  standardsCompliance: { passed: true, details: "Clean code" },
  issues: [{ severity: "blocker", description: "Edge case not handled in item.ts" }],
  remediation: "Add test for empty input",
  rawContent: '{"verdict":"rejected"}',
};

test("runTicketLifecycle: happy path resolves ticket on attempt 0 and commits to feature branch", async () => {
  const { repoDir, ticket } = setupMockWorkspace("auth-feature");

  try {
    ensureFeatureBranch({ workspaceDir: repoDir, featureSlug: "auth-feature" });

    let coderCalls = 0;
    const result = await runTicketLifecycle({
      workspaceDir: repoDir,
      featureSlug: "auth-feature",
      ticket,
      push: false,
      plannerRunner: async () => ({ plan: mockPlan, messages: [] }),
      coderRunner: async () => {
        coderCalls++;
        fs.writeFileSync(path.join(repoDir, "src-item.txt"), "built item", "utf-8");
        return { summary: "Implemented", messages: [] };
      },
      verifierRunner: async () => ({
        passed: true,
        totalCommands: 1,
        passedCommands: 1,
        failedCommands: 0,
        results: [],
        summary: "### Verification Summary: PASSED",
        durationMs: 10,
      }),
      reviewerRunner: async () => ({ verdict: mockPassingReview, messages: [] }),
    });

    assert.equal(result.status, "resolved");
    assert.equal(result.retriesUsed, 0);
    assert.equal(coderCalls, 1);
    assert.ok(result.commitSha);
    assert.equal(result.branch, "factory/auth-feature");

    // plan.md must be saved in .scratch/auth-feature/plan.md
    const planFile = path.join(repoDir, ".scratch", "auth-feature", "plan.md");
    assert.ok(fs.existsSync(planFile));

    // Ticket file must be updated inline
    const ticketOnDisk = fs.readFileSync(ticket.filePath, "utf-8");
    assert.match(ticketOnDisk, /\*{0,2}Status(?::\*{0,2}|\*{0,2}:)\s*resolved/i);
    assert.match(ticketOnDisk, /\*{0,2}Commit(?::\*{0,2}|\*{0,2}:)\s*[a-f0-9]+/i);
    assert.match(ticketOnDisk, /\*{0,2}Branch(?::\*{0,2}|\*{0,2}:)\s*factory\/auth-feature/i);
    assert.ok(ticketOnDisk.includes("Quality Gate Audit"));
  } finally {
    fs.rmSync(repoDir, { recursive: true, force: true });
  }
});

test("runTicketLifecycle: self-corrects when verifier fails on attempt 0 and passes on retry 1", async () => {
  const { repoDir, ticket } = setupMockWorkspace("retry-feature");

  try {
    ensureFeatureBranch({ workspaceDir: repoDir, featureSlug: "retry-feature" });

    let coderAttempts = 0;
    const receivedDiagnostics: (string | undefined)[] = [];

    const result = await runTicketLifecycle({
      workspaceDir: repoDir,
      featureSlug: "retry-feature",
      ticket,
      push: false,
      plannerRunner: async () => ({ plan: mockPlan, messages: [] }),
      coderRunner: async (opts) => {
        coderAttempts++;
        receivedDiagnostics.push(opts.diagnostics);
        fs.writeFileSync(path.join(repoDir, "file.txt"), `attempt ${coderAttempts}`, "utf-8");
        return { summary: "Implemented", messages: [] };
      },
      verifierRunner: async () => {
        if (coderAttempts === 1) {
          return {
            passed: false,
            totalCommands: 1,
            passedCommands: 0,
            failedCommands: 1,
            results: [],
            summary: "### Verification Summary: FAILED\nAssertion failed: expected 1 to be 2",
            durationMs: 15,
          };
        }
        return {
          passed: true,
          totalCommands: 1,
          passedCommands: 1,
          failedCommands: 0,
          results: [],
          summary: "### Verification Summary: PASSED",
          durationMs: 10,
        };
      },
      reviewerRunner: async () => ({ verdict: mockPassingReview, messages: [] }),
    });

    assert.equal(result.status, "resolved");
    assert.equal(result.retriesUsed, 1);
    assert.equal(coderAttempts, 2);
    assert.equal(receivedDiagnostics[0], undefined);
    assert.ok(receivedDiagnostics[1]?.includes("Assertion failed: expected 1 to be 2"));
  } finally {
    fs.rmSync(repoDir, { recursive: true, force: true });
  }
});

test("runTicketLifecycle: self-corrects when reviewer rejects on attempt 0 and approves on retry 1", async () => {
  const { repoDir, ticket } = setupMockWorkspace("review-retry-feature");

  try {
    ensureFeatureBranch({ workspaceDir: repoDir, featureSlug: "review-retry-feature" });

    let coderAttempts = 0;
    const receivedDiagnostics: (string | undefined)[] = [];

    const result = await runTicketLifecycle({
      workspaceDir: repoDir,
      featureSlug: "review-retry-feature",
      ticket,
      push: false,
      plannerRunner: async () => ({ plan: mockPlan, messages: [] }),
      coderRunner: async (opts) => {
        coderAttempts++;
        receivedDiagnostics.push(opts.diagnostics);
        fs.writeFileSync(path.join(repoDir, "file.txt"), `attempt ${coderAttempts}`, "utf-8");
        return { summary: "Implemented", messages: [] };
      },
      verifierRunner: async () => ({
        passed: true,
        totalCommands: 1,
        passedCommands: 1,
        failedCommands: 0,
        results: [],
        summary: "### Verification Summary: PASSED",
        durationMs: 10,
      }),
      reviewerRunner: async () => {
        if (coderAttempts === 1) {
          return { verdict: mockRejectingReview, messages: [] };
        }
        return { verdict: mockPassingReview, messages: [] };
      },
    });

    assert.equal(result.status, "resolved");
    assert.equal(result.retriesUsed, 1);
    assert.equal(coderAttempts, 2);
    assert.ok(receivedDiagnostics[1]?.includes("Edge case not handled"));
  } finally {
    fs.rmSync(repoDir, { recursive: true, force: true });
  }
});

test("runTicketLifecycle: marks ready-for-human and commits diagnostics when max 2 retries exhausted", async () => {
  const { repoDir, ticket } = setupMockWorkspace("exhaust-feature");

  try {
    ensureFeatureBranch({ workspaceDir: repoDir, featureSlug: "exhaust-feature" });

    let coderAttempts = 0;
    const result = await runTicketLifecycle({
      workspaceDir: repoDir,
      featureSlug: "exhaust-feature",
      ticket,
      maxRetries: 2,
      push: false,
      plannerRunner: async () => ({ plan: mockPlan, messages: [] }),
      coderRunner: async () => {
        coderAttempts++;
        fs.writeFileSync(path.join(repoDir, "broken.txt"), `broken ${coderAttempts}`, "utf-8");
        return { summary: "Tried to fix", messages: [] };
      },
      verifierRunner: async () => ({
        passed: false,
        totalCommands: 1,
        passedCommands: 0,
        failedCommands: 1,
        results: [],
        summary: "### Verification Summary: FAILED\nSyntaxError: Unexpected token",
        durationMs: 12,
      }),
      reviewerRunner: async () => ({ verdict: mockPassingReview, messages: [] }),
    });

    assert.equal(result.status, "ready-for-human");
    assert.equal(result.retriesUsed, 2);
    assert.equal(coderAttempts, 3); // 1 initial + 2 retries

    // Ticket file must be updated to ready-for-human
    const ticketOnDisk = fs.readFileSync(ticket.filePath, "utf-8");
    assert.match(ticketOnDisk, /\*{0,2}Status(?::\*{0,2}|\*{0,2}:)\s*ready-for-human/i);
    assert.ok(ticketOnDisk.includes("SyntaxError: Unexpected token"));

    // Failure diagnostics must be committed
    const commitMsg = execSync("git log -n 1 --pretty=%B", {
      cwd: repoDir,
      encoding: "utf-8",
    }).trim();
    assert.ok(commitMsg.includes("ready-for-human"));
  } finally {
    fs.rmSync(repoDir, { recursive: true, force: true });
  }
});

test("runTicketLifecycle: integrates with GitHubIssueTracker (claims ticket, commits Fixes #<id>, resolves with audit comment)", async () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "sf-lifecycle-gh-"));
  execSync("git init -b main", { cwd: tmpDir, stdio: "ignore" });
  execSync('git config user.name "Test Runner"', { cwd: tmpDir, stdio: "ignore" });
  execSync('git config user.email "runner@example.com"', { cwd: tmpDir, stdio: "ignore" });
  fs.writeFileSync(path.join(tmpDir, "CONTEXT.md"), "# Domain Context\n", "utf-8");
  execSync("git add CONTEXT.md && git commit -m 'initial commit'", {
    cwd: tmpDir,
    stdio: "ignore",
  });

  const currentLabels = new Set<string>(["factory:ready"]);
  const commentsPosted: string[] = [];

  const client = new GitHubClient({
    token: "tok",
    owner: "org",
    repo: "repo",
    fetch: async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";

      if (url.includes("/issues/50/comments") && method === "POST") {
        const body = JSON.parse(String(init?.body));
        commentsPosted.push(body.body);
        return new Response(JSON.stringify({ id: 1, body: body.body }), { status: 201 });
      }
      if (url.includes("/issues/50") && method === "GET") {
        return new Response(
          JSON.stringify({
            id: 150,
            number: 50,
            title: "Build notification sender",
            body: "Blocked by: None\n\nNotification spec.",
            state: "open",
            labels: Array.from(currentLabels).map((name) => ({ name })),
          }),
          { status: 200 }
        );
      }
      if (url.includes("/issues/50") && method === "PATCH") {
        const body = JSON.parse(String(init?.body));
        if (body.labels) {
          currentLabels.clear();
          for (const l of body.labels) currentLabels.add(l);
        }
        return new Response(
          JSON.stringify({ id: 150, number: 50, labels: Array.from(currentLabels) }),
          { status: 200 }
        );
      }
      return new Response("Not found", { status: 404 });
    },
  });

  const tracker = new GitHubIssueTracker({ client });
  const ticket: Ticket = {
    id: "50",
    number: 50,
    slug: "build-notification-sender",
    title: "Build notification sender",
    filePath: "https://github.com/org/repo/issues/50",
    status: "ready-for-agent",
    blockedBy: [],
  };

  try {
    ensureFeatureBranch({ workspaceDir: tmpDir, branch: "factory/notifications" });

    const result = await runTicketLifecycle({
      workspaceDir: tmpDir,
      featureSlug: "notifications",
      ticket,
      tracker,
      push: false,
      plannerRunner: async () => ({ plan: mockPlan, messages: [] }),
      coderRunner: async () => {
        fs.writeFileSync(path.join(tmpDir, "notifier.ts"), "export const send = () => {};\n");
        return { summary: "Implemented notifier", messages: [] };
      },
      verifierRunner: async () => ({
        passed: true,
        totalCommands: 1,
        passedCommands: 1,
        failedCommands: 0,
        results: [],
        summary: "All tests passed",
        durationMs: 5,
      }),
      reviewerRunner: async () => ({ verdict: mockPassingReview, messages: [] }),
    });

    assert.equal(result.status, "resolved");
    assert.ok(currentLabels.has("factory:resolved"));
    assert.ok(!currentLabels.has("factory:claimed"));

    // Check git commit message has Fixes #50
    const log = execSync("git log -n 1 --pretty=%B", {
      cwd: tmpDir,
      encoding: "utf-8",
    }).trim();
    assert.ok(log.includes("Fixes #50"));

    // Audit comment posted to GitHub issue
    assert.equal(commentsPosted.length, 1);
    assert.ok(commentsPosted[0].includes("Quality Gate Audit"));
    assert.ok(commentsPosted[0].includes("Implementation Plan"));
    assert.ok(commentsPosted[0].includes("Deterministic Verification"));
    assert.ok(commentsPosted[0].includes("Reviewer Verdict"));
    assert.ok(commentsPosted[0].includes(result.commitSha!));
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

