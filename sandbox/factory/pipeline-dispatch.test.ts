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

test("runAssemblyLinePipeline: ad-hoc single issue dispatch operates on factory/issue-<id> and opens isolated PR", async () => {
  const repoDir = fs.mkdtempSync(path.join(os.tmpdir(), "sf-pipeline-gh-adhoc-"));
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

  const issue = {
    id: 99,
    number: 99,
    title: "Fix critical login vulnerability",
    body: "Blocked by: None\n\nFix security bug in auth parser.",
    state: "open",
    labels: [{ name: "security" }],
  };

  const labels = new Set<string>(["security"]);
  const comments: string[] = [];
  let prCreated: any = null;
  const currentPr = {
    id: 902,
    number: 606,
    title: "feat: resolve #99 - Fix critical login vulnerability",
    body: "",
    state: "open",
    draft: true,
    html_url: "https://github.com/org/repo/pull/606",
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
        return new Response(JSON.stringify([]), { status: 200 }); // No milestones
      }
      if (url.includes("/issues/99/comments") && method === "POST") {
        const body = JSON.parse(String(init?.body));
        comments.push(body.body);
        return new Response(JSON.stringify({ id: 1, body: body.body }), { status: 201 });
      }
      if (url.includes("/issues/606/comments") && method === "POST") {
        const body = JSON.parse(String(init?.body));
        prComments.push(body.body);
        return new Response(JSON.stringify({ id: 1, body: body.body }), { status: 201 });
      }
      if (url.includes("/issues/99") && method === "GET") {
        return new Response(
          JSON.stringify({
            ...issue,
            labels: Array.from(labels).map((name) => ({ name })),
          }),
          { status: 200 }
        );
      }
      if (url.includes("/issues/99") && method === "PATCH") {
        const body = JSON.parse(String(init?.body));
        if (body.labels) {
          labels.clear();
          for (const l of body.labels) labels.add(l);
        }
        return new Response(
          JSON.stringify({
            id: 99,
            number: 99,
            labels: Array.from(labels).map((name) => ({ name })),
          }),
          { status: 200 }
        );
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
      if (url.includes("/pulls/606") && method === "PATCH") {
        const body = JSON.parse(String(init?.body));
        if (body.draft !== undefined) currentPr.draft = body.draft;
        if (body.body !== undefined) currentPr.body = body.body;
        return new Response(JSON.stringify(currentPr), { status: 200 });
      }

      return new Response("Not found", { status: 404 });
    },
  });

  const tracker = new GitHubIssueTracker({ client });

  try {
    const { result, envelopes } = await captureContainerOutput(async () => {
      return runAssemblyLinePipeline({
        workspaceDir: repoDir,
        issueId: "99",
        tracker,
        push: false,
        plannerRunner: async () => ({ plan: mockPlan, messages: [] }),
        coderRunner: async () => {
          fs.writeFileSync(path.join(repoDir, "auth.ts"), "export const safe = true;\n");
          return { summary: "Secured", messages: [] };
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

    // 1. Operates on branch factory/issue-99
    assert.equal(result.branch, "factory/issue-99");
    assert.equal(result.allResolved, true);

    // 2. Draft PR created targeting main on branch factory/issue-99
    assert.ok(prCreated);
    assert.equal(prCreated.head, "factory/issue-99");
    assert.equal(prCreated.base, "main");
    assert.ok(prCreated.body.includes("Fixes #99"));

    // 3. PR finalized to ready-for-review
    assert.equal(currentPr.draft, false);

    // 4. Issue 99 labeled factory:resolved
    assert.ok(labels.has("factory:resolved"));
    assert.ok(comments[0].includes("Quality Gate Audit"));

    // 5. Git log has Fixes #99
    const log = execSync("git log -n 1 --pretty=%B", {
      cwd: repoDir,
      encoding: "utf-8",
    }).trim();
    assert.ok(log.includes("Fixes #99"));

    // 6. Delivery gate telemetry emitted for init and finalize
    const gateEvents = envelopes.filter(
      (e): e is TelemetryEnvelope<DeliveryGateEventData> => e.type === "delivery_gate"
    );
    assert.equal(gateEvents.length, 2);
    assert.equal(gateEvents[0].data.draft, true);
    assert.equal(gateEvents[0].data.pullRequestNumber, 606);
    assert.equal(gateEvents[0].data.branch, "factory/issue-99");
    assert.equal(gateEvents[0].data.pullRequestUrl, "https://github.com/org/repo/pull/606");
    assert.equal(gateEvents[1].data.ready_for_review, true);
    assert.equal(gateEvents[1].data.pullRequestNumber, 606);
    assert.equal(gateEvents[1].data.branch, "factory/issue-99");
  } finally {
    fs.rmSync(repoDir, { recursive: true, force: true });
  }
});

test("runAssemblyLinePipeline: emits delivery_gate telemetry envelopes over container output during gate initialization and finalization", async () => {
  const repoDir = fs.mkdtempSync(path.join(os.tmpdir(), "sf-pipeline-telemetry-gate-"));
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
    id: 70,
    number: 70,
    title: "telemetry-feature",
    description: "Spec for telemetry",
    state: "open",
    open_issues: 1,
    closed_issues: 0,
  };

  const issues = [
    {
      id: 701,
      number: 71,
      title: "Gate Ticket One",
      body: "Blocked by: None\n\nImplement telemetry gate.",
      state: "open",
      labels: [{ name: "factory:ready" }],
    },
  ];

  const currentPr = {
    id: 7000,
    number: 707,
    title: "feat(telemetry-feature): implement telemetry-feature",
    body: "",
    state: "open",
    draft: true,
    html_url: "https://github.com/org/repo/pull/707",
  };

  const labels = new Set<string>(["factory:ready"]);

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
      if (url.includes("/issues?milestone=70")) {
        return new Response(
          JSON.stringify([
            {
              ...issues[0],
              labels: Array.from(labels).map((name) => ({ name })),
            },
          ]),
          { status: 200 }
        );
      }
      if (url.includes("/pulls") && method === "GET") {
        return new Response(JSON.stringify([currentPr]), { status: 200 });
      }
      if (url.includes("/pulls") && method === "POST") {
        const body = JSON.parse(String(init?.body));
        currentPr.title = body.title;
        currentPr.body = body.body;
        currentPr.draft = body.draft;
        return new Response(JSON.stringify(currentPr), { status: 201 });
      }
      if (url.includes("/pulls/707") && method === "PATCH") {
        const body = JSON.parse(String(init?.body));
        if (body.draft !== undefined) currentPr.draft = body.draft;
        if (body.body !== undefined) currentPr.body = body.body;
        return new Response(JSON.stringify(currentPr), { status: 200 });
      }
      if (url.includes("/issues/71/comments") && method === "POST") {
        return new Response(JSON.stringify({ id: 1 }), { status: 201 });
      }
      if (url.includes("/issues/707/comments") && method === "POST") {
        return new Response(JSON.stringify({ id: 2 }), { status: 201 });
      }
      if (url.includes("/issues/71") && method === "GET") {
        return new Response(
          JSON.stringify({
            ...issues[0],
            labels: Array.from(labels).map((name) => ({ name })),
          }),
          { status: 200 }
        );
      }
      if (url.includes("/issues/71") && method === "PATCH") {
        const body = JSON.parse(String(init?.body));
        if (body.labels) {
          labels.clear();
          for (const l of body.labels) labels.add(l);
        }
        return new Response(
          JSON.stringify({
            ...issues[0],
            labels: Array.from(labels).map((name) => ({ name })),
          }),
          { status: 200 }
        );
      }

      return new Response("Not found", { status: 404 });
    },
  });

  const tracker = new GitHubIssueTracker({ client });

  try {
    const { result, envelopes } = await captureContainerOutput(async () => {
      return runAssemblyLinePipeline({
        workspaceDir: repoDir,
        featureSlug: "telemetry-feature",
        tracker,
        push: false,
        plannerRunner: async () => ({ plan: mockPlan, messages: [] }),
        coderRunner: async () => {
          fs.writeFileSync(path.join(repoDir, "gate.txt"), "gate passed\n");
          return { summary: "Implemented", messages: [] };
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

    assert.equal(result.allResolved, true);

    const gateEvents = envelopes.filter(
      (e): e is TelemetryEnvelope<DeliveryGateEventData> => e.type === "delivery_gate"
    );

    // Must emit at least two delivery_gate events: one upon init, one upon finalize
    assert.ok(
      gateEvents.length >= 2,
      `Expected at least 2 delivery_gate events, got ${gateEvents.length}`
    );

    // 1. Initialization event: contains pull request number, HTML URL, branch, title, and draft: true
    const initEvent = gateEvents.find((e) => e.data.draft === true);
    assert.ok(initEvent, "Expected a delivery_gate event with draft: true");
    assert.equal(initEvent.data.pullRequestNumber, 707);
    assert.equal(initEvent.data.pullRequestUrl, "https://github.com/org/repo/pull/707");
    assert.equal(initEvent.data.branch, "factory/telemetry-feature");
    assert.ok(initEvent.data.title);
    assert.equal(initEvent.data.draft, true);

    // 2. Finalization event: contains pull request number, HTML URL, branch, and ready_for_review: true
    const finalizeEvent = gateEvents.find((e) => e.data.ready_for_review === true);
    assert.ok(finalizeEvent, "Expected a delivery_gate event with ready_for_review: true");
    assert.equal(finalizeEvent.data.pullRequestNumber, 707);
    assert.equal(finalizeEvent.data.pullRequestUrl, "https://github.com/org/repo/pull/707");
    assert.equal(finalizeEvent.data.branch, "factory/telemetry-feature");
    assert.equal(finalizeEvent.data.ready_for_review, true);
  } finally {
    fs.rmSync(repoDir, { recursive: true, force: true });
  }
});
