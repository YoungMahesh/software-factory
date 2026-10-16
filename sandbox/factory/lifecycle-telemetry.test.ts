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
import { parseTelemetryEnvelope } from "./events.ts";

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

test("runTicketLifecycle: emits attempt_start telemetry event for test failure and reviewer rejection during self-correction loops", async () => {
  const { repoDir, ticket } = setupMockWorkspace("telemetry-retry-feature");

  try {
    ensureFeatureBranch({ workspaceDir: repoDir, featureSlug: "telemetry-retry-feature" });

    const emittedEnvelopes: any[] = [];
    const mockStream = {
      write: (chunk: string) => {
        const env = parseTelemetryEnvelope(chunk);
        if (env) emittedEnvelopes.push(env);
        return true;
      },
    };

    let coderAttempts = 0;
    const result = await runTicketLifecycle({
      workspaceDir: repoDir,
      featureSlug: "telemetry-retry-feature",
      ticket,
      push: false,
      stream: mockStream,
      plannerRunner: async () => ({ plan: mockPlan, messages: [] }),
      coderRunner: async () => {
        coderAttempts++;
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
            summary: "Assertion failed: expected true to be false",
            durationMs: 15,
          };
        }
        return {
          passed: true,
          totalCommands: 1,
          passedCommands: 1,
          failedCommands: 0,
          results: [],
          summary: "All tests passed",
          durationMs: 10,
        };
      },
      reviewerRunner: async () => ({ verdict: mockPassingReview, messages: [] }),
    });

    assert.equal(result.status, "resolved");
    assert.equal(coderAttempts, 2);

    const attemptEvents = emittedEnvelopes.filter((e) => e.type === "attempt_start");
    assert.equal(attemptEvents.length, 2, "Must emit attempt_start on each loop iteration");

    // Attempt 1: initial
    assert.equal(attemptEvents[0].data.attempt, 1);
    assert.equal(attemptEvents[0].data.maxRetries, 2);

    // Attempt 2: test failure retry
    assert.equal(attemptEvents[1].data.attempt, 2);
    assert.equal(attemptEvents[1].data.maxRetries, 2);
    assert.equal(attemptEvents[1].data.reason, "test failure");
    assert.ok(attemptEvents[1].data.diagnostics?.includes("Assertion failed: expected true to be false"));
  } finally {
    fs.rmSync(repoDir, { recursive: true, force: true });
  }
});

test("runTicketLifecycle: emits reviewer_rejection telemetry event when reviewer rejects diff", async () => {
  const { repoDir, ticket } = setupMockWorkspace("telemetry-review-reject");

  try {
    ensureFeatureBranch({ workspaceDir: repoDir, featureSlug: "telemetry-review-reject" });

    const emittedEnvelopes: any[] = [];
    const mockStream = {
      write: (chunk: string) => {
        const env = parseTelemetryEnvelope(chunk);
        if (env) emittedEnvelopes.push(env);
        return true;
      },
    };

    let coderAttempts = 0;
    const result = await runTicketLifecycle({
      workspaceDir: repoDir,
      featureSlug: "telemetry-review-reject",
      ticket,
      push: false,
      stream: mockStream,
      plannerRunner: async () => ({ plan: mockPlan, messages: [] }),
      coderRunner: async () => {
        coderAttempts++;
        fs.writeFileSync(path.join(repoDir, "file.txt"), `attempt ${coderAttempts}`, "utf-8");
        return { summary: "Implemented", messages: [] };
      },
      verifierRunner: async () => ({
        passed: true,
        totalCommands: 1,
        passedCommands: 1,
        failedCommands: 0,
        results: [],
        summary: "All tests passed",
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
    assert.equal(coderAttempts, 2);

    // Verify reviewer_rejection event
    const rejectionEvents = emittedEnvelopes.filter((e) => e.type === "reviewer_rejection");
    assert.equal(rejectionEvents.length, 1, "Must emit reviewer_rejection event");
    assert.equal(rejectionEvents[0].stage, "REVIEWER");
    assert.equal(rejectionEvents[0].data.verdict, "rejected");
    assert.equal(rejectionEvents[0].data.summary, "Missing edge case tests");
    assert.equal(rejectionEvents[0].data.remediation, "Add test for empty input");

    // Verify second attempt_start has reviewer rejection reason
    const attemptEvents = emittedEnvelopes.filter((e) => e.type === "attempt_start");
    assert.equal(attemptEvents.length, 2);
    assert.equal(attemptEvents[1].data.attempt, 2);
    assert.equal(attemptEvents[1].data.reason, "reviewer rejection");
    assert.ok(attemptEvents[1].data.diagnostics?.includes("Reviewer Rejection: REJECTED"));
  } finally {
    fs.rmSync(repoDir, { recursive: true, force: true });
  }
});
