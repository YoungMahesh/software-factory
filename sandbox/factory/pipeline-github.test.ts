import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import { execSync } from "node:child_process";
import { runAssemblyLinePipeline } from "./pipeline.ts";
import { PreflightError } from "./preflight.ts";
import { type ImplementationPlan, type ReviewVerdict } from "./harness.ts";
import { GitHubClient } from "./github.ts";
import { GitHubIssueTracker } from "./tracker/github-tracker.ts";
import {
  parseTelemetryEnvelope,
  setGlobalTelemetryStream,
  type TelemetryEnvelope,
  type DeliveryGateEventData,
} from "./events.ts";
import {
  captureContainerOutput,
  setupRepoWithPrereqs,
  addTicket,
  mockPlan,
  mockPassingReview,
} from "./pipeline-test-helpers.ts";

test("runAssemblyLinePipeline: multi-ticket batch lifecycle with GitHub tracker (draft PR creation, incremental update, and ready-for-review finalization)", async () => {
  const repoDir = fs.mkdtempSync(path.join(os.tmpdir(), "sf-pipeline-gh-batch-"));
  execSync("git init -b main", { cwd: repoDir, stdio: "ignore" });
  execSync('git config user.name "Pipeline Test"', { cwd: repoDir, stdio: "ignore" });
  execSync('git config user.email "pipe@example.com"', { cwd: repoDir, stdio: "ignore" });
  fs.writeFileSync(path.join(repoDir, "CONTEXT.md"), "# Domain Context\n", "utf-8");
  const adrDir = path.join(repoDir, "docs", "adr");
  fs.mkdirSync(adrDir, { recursive: true });
  fs.writeFileSync(
    path.join(adrDir, "0001-init.md"),
    "# 0001: Architecture\n\n**Status**: Accepted\n",
    "utf-8"
  );
  execSync("git add . && git commit -m 'initial commit'", { cwd: repoDir, stdio: "ignore" });

  const milestone = {
    id: 1,
    number: 10,
    title: "auth-batch",
    description: "Milestone spec for auth batch",
    state: "open",
    open_issues: 2,
    closed_issues: 0,
  };

  const issues = [
    {
      id: 101,
      number: 1,
      title: "Ticket One",
      body: "Blocked by: None\n\nCreate models.",
      state: "open",
      labels: [{ name: "factory:ready" }],
    },
    {
      id: 102,
      number: 2,
      title: "Ticket Two",
      body: "Blocked by: #1\n\nCreate endpoints.",
      state: "open",
      labels: [{ name: "factory:ready" }],
    },
  ];

  const issueLabels = new Map<number, Set<string>>([
    [1, new Set(["factory:ready"])],
    [2, new Set(["factory:ready"])],
  ]);

  const issueComments = new Map<number, string[]>();
  let prCreated: any = null;
  let prUpdates: any[] = [];
  const currentPr = {
    id: 900,
    number: 404,
    title: "feat(auth-batch): implement auth-batch",
    body: "",
    state: "open",
    draft: true,
    html_url: "https://github.com/org/repo/pull/404",
  };
  const prComments: string[] = [];

  const client = new GitHubClient({
    token: "tok",
    owner: "org",
    repo: "repo",
    fetch: async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";

      if (url.includes("/milestones")) {
        return new Response(JSON.stringify([milestone]), { status: 200 });
      }
      if (url.includes("/issues?milestone=10")) {
        return new Response(
          JSON.stringify(
            issues.map((i) => ({
              ...i,
              labels: Array.from(issueLabels.get(i.number) ?? []).map((name) => ({ name })),
            }))
          ),
          { status: 200 }
        );
      }
      if (url.includes("/issues/404/comments") && method === "POST") {
        const body = JSON.parse(String(init?.body));
        prComments.push(body.body);
        return new Response(JSON.stringify({ id: 1, body: body.body }), { status: 201 });
      }
      for (const num of [1, 2]) {
        if (url.includes(`/issues/${num}/comments`) && method === "POST") {
          const body = JSON.parse(String(init?.body));
          if (!issueComments.has(num)) issueComments.set(num, []);
          issueComments.get(num)!.push(body.body);
          return new Response(JSON.stringify({ id: 1, body: body.body }), { status: 201 });
        }
        if (url.includes(`/issues/${num}`) && method === "GET") {
          const iss = issues.find((i) => i.number === num)!;
          return new Response(
            JSON.stringify({
              ...iss,
              labels: Array.from(issueLabels.get(num) ?? []).map((name) => ({ name })),
            }),
            { status: 200 }
          );
        }
        if (url.includes(`/issues/${num}`) && method === "PATCH") {
          const body = JSON.parse(String(init?.body));
          if (body.labels) {
            issueLabels.set(num, new Set(body.labels));
          }
          return new Response(
            JSON.stringify({
              id: num,
              number: num,
              labels: Array.from(issueLabels.get(num) ?? []).map((name) => ({ name })),
            }),
            { status: 200 }
          );
        }
      }
      if (url.includes("/pulls") && method === "GET") {
        if (prCreated) {
          return new Response(JSON.stringify([currentPr]), { status: 200 });
        }
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (url.includes("/pulls") && method === "POST") {
        prCreated = JSON.parse(String(init?.body));
        currentPr.title = prCreated.title;
        currentPr.body = prCreated.body;
        currentPr.draft = prCreated.draft;
        return new Response(JSON.stringify(currentPr), { status: 201 });
      }
      if (url.includes("/pulls/404") && method === "PATCH") {
        const body = JSON.parse(String(init?.body));
        prUpdates.push(body);
        if (body.body !== undefined) currentPr.body = body.body;
        if (body.draft !== undefined) currentPr.draft = body.draft;
        return new Response(JSON.stringify(currentPr), { status: 200 });
      }

      return new Response("Not found", { status: 404 });
    },
  });

  const tracker = new GitHubIssueTracker({ client });

  try {
    const executedOrder: string[] = [];

    const { result, envelopes } = await captureContainerOutput(async () => {
      return runAssemblyLinePipeline({
        workspaceDir: repoDir,
        featureSlug: "auth-batch",
        tracker,
        push: false,
        plannerRunner: async ({ ticket }) => {
          const id = typeof ticket === "string" ? ticket : ticket.id;
          executedOrder.push(id);
          return { plan: mockPlan, messages: [] };
        },
        coderRunner: async ({ ticket }) => {
          const id = typeof ticket === "string" ? ticket : ticket.id;
          fs.writeFileSync(path.join(repoDir, `feature-${id}.txt`), `done ${id}\n`);
          return { summary: `Implemented ${id}`, messages: [] };
        },
        verifierRunner: async () => ({
          passed: true,
          totalCommands: 1,
          passedCommands: 1,
          failedCommands: 0,
          results: [],
          summary: "Verifier passed",
          durationMs: 5,
        }),
        reviewerRunner: async () => ({ verdict: mockPassingReview, messages: [] }),
      });
    });

    // 1. All frontier tickets resolved in order
    assert.deepEqual(executedOrder, ["1", "2"]);
    assert.equal(result.allResolved, true);
    assert.equal(result.haltedOnError, false);
    assert.equal(result.branch, "factory/auth-batch");

    // 2. Draft PR created on first ticket with Fixes #1
    assert.ok(prCreated);
    assert.equal(prCreated.draft, true);
    assert.equal(prCreated.head, "factory/auth-batch");
    assert.equal(prCreated.base, "main");
    assert.ok(prCreated.body.includes("Fixes #1: Ticket One"));

    // 3. Second ticket updated PR description with Fixes #2
    assert.ok(currentPr.body.includes("Fixes #2: Ticket Two"));

    // 4. Batch completion finalized PR (draft: false) and posted summary table
    assert.equal(currentPr.draft, false);
    assert.ok(prComments.length > 0);
    assert.ok(prComments[0].includes("Software Factory Assembly Line Summary"));

    // 5. Issues labeled factory:resolved and audit comments posted
    assert.ok(issueLabels.get(1)?.has("factory:resolved"));
    assert.ok(issueLabels.get(2)?.has("factory:resolved"));
    assert.ok(issueComments.get(1)?.[0].includes("Quality Gate Audit"));
    assert.ok(issueComments.get(2)?.[0].includes("Quality Gate Audit"));

    // 6. Delivery gate telemetry emitted for init and finalize
    const gateEvents = envelopes.filter(
      (e): e is TelemetryEnvelope<DeliveryGateEventData> => e.type === "delivery_gate"
    );
    assert.equal(gateEvents.length, 2);
    assert.equal(gateEvents[0].data.draft, true);
    assert.equal(gateEvents[0].data.pullRequestNumber, 404);
    assert.equal(gateEvents[0].data.branch, "factory/auth-batch");
    assert.equal(gateEvents[0].data.pullRequestUrl, "https://github.com/org/repo/pull/404");
    assert.equal(gateEvents[1].data.ready_for_review, true);
    assert.equal(gateEvents[1].data.pullRequestNumber, 404);
    assert.equal(gateEvents[1].data.branch, "factory/auth-batch");
  } finally {
    fs.rmSync(repoDir, { recursive: true, force: true });
  }
});

test("runAssemblyLinePipeline: multi-ticket batch halts safely and alerts PR when ticket fails after exhausted retries", async () => {
  const repoDir = fs.mkdtempSync(path.join(os.tmpdir(), "sf-pipeline-gh-fail-"));
  execSync("git init -b main", { cwd: repoDir, stdio: "ignore" });
  execSync('git config user.name "Pipeline Test"', { cwd: repoDir, stdio: "ignore" });
  execSync('git config user.email "pipe@example.com"', { cwd: repoDir, stdio: "ignore" });
  fs.writeFileSync(path.join(repoDir, "CONTEXT.md"), "# Domain Context\n", "utf-8");
  const adrDir = path.join(repoDir, "docs", "adr");
  fs.mkdirSync(adrDir, { recursive: true });
  fs.writeFileSync(
    path.join(adrDir, "0001-init.md"),
    "# 0001: Architecture\n\n**Status**: Accepted\n",
    "utf-8"
  );
  execSync("git add . && git commit -m 'initial commit'", { cwd: repoDir, stdio: "ignore" });

  const milestone = {
    id: 2,
    number: 20,
    title: "broken-batch",
    description: "Spec",
    state: "open",
    open_issues: 2,
    closed_issues: 0,
  };

  const issues = [
    {
      id: 201,
      number: 10,
      title: "Good Ticket",
      body: "Blocked by: None",
      state: "open",
      labels: [{ name: "factory:ready" }],
    },
    {
      id: 202,
      number: 11,
      title: "Bad Ticket",
      body: "Blocked by: #10",
      state: "open",
      labels: [{ name: "factory:ready" }],
    },
  ];

  const issueLabels = new Map<number, Set<string>>([
    [10, new Set(["factory:ready"])],
    [11, new Set(["factory:ready"])],
  ]);

  const issueComments = new Map<number, string[]>();
  let prCreated: any = null;
  const currentPr = {
    id: 901,
    number: 505,
    title: "feat(broken-batch): implement broken-batch",
    body: "",
    state: "open",
    draft: true,
    html_url: "https://github.com/org/repo/pull/505",
  };
  const prComments: string[] = [];

  const client = new GitHubClient({
    token: "tok",
    owner: "org",
    repo: "repo",
    fetch: async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";

      if (url.includes("/milestones")) {
        return new Response(JSON.stringify([milestone]), { status: 200 });
      }
      if (url.includes("/issues?milestone=20")) {
        return new Response(
          JSON.stringify(
            issues.map((i) => ({
              ...i,
              labels: Array.from(issueLabels.get(i.number) ?? []).map((name) => ({ name })),
            }))
          ),
          { status: 200 }
        );
      }
      if (url.includes("/issues/505/comments") && method === "POST") {
        const body = JSON.parse(String(init?.body));
        prComments.push(body.body);
        return new Response(JSON.stringify({ id: 1, body: body.body }), { status: 201 });
      }
      for (const num of [10, 11]) {
        if (url.includes(`/issues/${num}/comments`) && method === "POST") {
          const body = JSON.parse(String(init?.body));
          if (!issueComments.has(num)) issueComments.set(num, []);
          issueComments.get(num)!.push(body.body);
          return new Response(JSON.stringify({ id: 1, body: body.body }), { status: 201 });
        }
        if (url.includes(`/issues/${num}`) && method === "GET") {
          const iss = issues.find((i) => i.number === num)!;
          return new Response(
            JSON.stringify({
              ...iss,
              labels: Array.from(issueLabels.get(num) ?? []).map((name) => ({ name })),
            }),
            { status: 200 }
          );
        }
        if (url.includes(`/issues/${num}`) && method === "PATCH") {
          const body = JSON.parse(String(init?.body));
          if (body.labels) {
            issueLabels.set(num, new Set(body.labels));
          }
          return new Response(
            JSON.stringify({
              id: num,
              number: num,
              labels: Array.from(issueLabels.get(num) ?? []).map((name) => ({ name })),
            }),
            { status: 200 }
          );
        }
      }
      if (url.includes("/pulls") && method === "GET") {
        if (prCreated) {
          return new Response(JSON.stringify([currentPr]), { status: 200 });
        }
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (url.includes("/pulls") && method === "POST") {
        prCreated = JSON.parse(String(init?.body));
        currentPr.title = prCreated.title;
        currentPr.body = prCreated.body;
        currentPr.draft = prCreated.draft;
        return new Response(JSON.stringify(currentPr), { status: 201 });
      }
      if (url.includes("/pulls/505") && method === "PATCH") {
        const body = JSON.parse(String(init?.body));
        if (body.body !== undefined) currentPr.body = body.body;
        if (body.draft !== undefined) currentPr.draft = body.draft;
        return new Response(JSON.stringify(currentPr), { status: 200 });
      }

      return new Response("Not found", { status: 404 });
    },
  });

  const tracker = new GitHubIssueTracker({ client });

  try {
    const result = await runAssemblyLinePipeline({
      workspaceDir: repoDir,
      featureSlug: "broken-batch",
      tracker,
      maxRetries: 2,
      push: false,
      plannerRunner: async () => ({ plan: mockPlan, messages: [] }),
      coderRunner: async () => ({ summary: "Coded", messages: [] }),
      verifierRunner: async ({ commands }) => {
        // Ticket 10 passes, Ticket 11 fails
        if (issueLabels.get(10)?.has("factory:resolved")) {
          return {
            passed: false,
            totalCommands: 1,
            passedCommands: 0,
            failedCommands: 1,
            results: [],
            summary: "AssertionError: verification failed",
            durationMs: 5,
          };
        }
        return {
          passed: true,
          totalCommands: 1,
          passedCommands: 1,
          failedCommands: 0,
          results: [],
          summary: "Verifier passed",
          durationMs: 5,
        };
      },
      reviewerRunner: async () => ({ verdict: mockPassingReview, messages: [] }),
    });

    assert.equal(result.haltedOnError, true);
    assert.equal(result.allResolved, false);

    // Ticket 10 is resolved
    assert.ok(issueLabels.get(10)?.has("factory:resolved"));
    // Ticket 11 is labeled factory:ready-for-human with diagnostics comment
    assert.ok(issueLabels.get(11)?.has("factory:ready-for-human"));
    assert.ok(issueComments.get(11)?.[0].includes("Failure Diagnostics"));

    // PR description has alert added
    assert.ok(currentPr.body.includes("Software Factory Alert"));
    assert.ok(currentPr.body.includes("Bad Ticket"));

    // PR has alert comment added
    assert.ok(prComments.some((c) => c.includes("Bad Ticket") && c.includes("AssertionError")));

    // Execution halted safely, PR remains in Draft mode (not marked ready for review)
    assert.equal(currentPr.draft, true);
  } finally {
    fs.rmSync(repoDir, { recursive: true, force: true });
  }
});
