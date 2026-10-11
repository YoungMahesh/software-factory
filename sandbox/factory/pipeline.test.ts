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

function setupRepoWithPrereqs(featureSlug: string): string {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "sf-pipeline-test-"));
  execSync("git init -b main", { cwd: tmpDir, stdio: "ignore" });
  execSync('git config user.name "Pipeline Test"', { cwd: tmpDir, stdio: "ignore" });
  execSync('git config user.email "pipe@example.com"', { cwd: tmpDir, stdio: "ignore" });

  fs.writeFileSync(path.join(tmpDir, "README.md"), "# Pipeline Test\n", "utf-8");
  fs.writeFileSync(path.join(tmpDir, "CONTEXT.md"), "# Domain Context\n\nGlossary here.\n", "utf-8");
  fs.writeFileSync(path.join(tmpDir, "AGENTS.md"), "# Agent Instructions\n\n## Agent skills\n\nSkills.\n", "utf-8");
  const adrDir = path.join(tmpDir, "docs", "adr");
  fs.mkdirSync(adrDir, { recursive: true });
  fs.writeFileSync(
    path.join(adrDir, "0001-init.md"),
    "# 0001: Architecture\n\n**Status**: Accepted\n\nInitial architecture.\n",
    "utf-8"
  );

  const featureDir = path.join(tmpDir, ".scratch", featureSlug);
  const issuesDir = path.join(featureDir, "issues");
  fs.mkdirSync(issuesDir, { recursive: true });

  fs.writeFileSync(path.join(featureDir, "spec.md"), `# Spec: ${featureSlug}\n\nFeature spec.\n`, "utf-8");

  execSync("git add . && git commit -m 'initial repo with prerequisites'", {
    cwd: tmpDir,
    stdio: "ignore",
  });

  return tmpDir;
}

function addTicket(repoDir: string, featureSlug: string, id: string, title: string, blockedBy: string = "None"): string {
  const ticketPath = path.join(repoDir, ".scratch", featureSlug, "issues", `${id}-${title.toLowerCase().replace(/\s+/g, "-")}.md`);
  const content = `# ${id}: ${title}

**What to build:** ${title}

**Blocked by:** ${blockedBy}

**Status:** ready-for-agent

- [ ] Task
`;
  fs.writeFileSync(ticketPath, content, "utf-8");
  execSync(`git add "${ticketPath}" && git commit -m "add ticket ${id}"`, { cwd: repoDir, stdio: "ignore" });
  return ticketPath;
}

const mockPlan: ImplementationPlan = {
  ticketId: "mock",
  summary: "Mock plan",
  affectedFiles: ["app.ts"],
  testCommands: ["echo 'test passed'"],
  steps: ["step 1"],
  rawContent: "```json\n{}\n```",
};

const mockPassingReview: ReviewVerdict = {
  verdict: "approved",
  summary: "Clean implementation",
  specCompliance: { passed: true, details: "Pass" },
  standardsCompliance: { passed: true, details: "Pass" },
  issues: [],
  rawContent: "{}",
};

test("runAssemblyLinePipeline: throws PreflightError if repository prerequisites are missing", async () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "sf-pipeline-bad-"));
  execSync("git init -b main", { cwd: tmpDir, stdio: "ignore" });
  execSync('git config user.name "Test"', { cwd: tmpDir, stdio: "ignore" });
  execSync('git config user.email "test@example.com"', { cwd: tmpDir, stdio: "ignore" });
  execSync("git commit --allow-empty -m 'initial commit'", { cwd: tmpDir, stdio: "ignore" });

  try {
    await assert.rejects(
      async () => {
        await runAssemblyLinePipeline({
          workspaceDir: tmpDir,
          featureSlug: "bad-feature",
          push: false,
        });
      },
      (err: any) => {
        assert.ok(err instanceof PreflightError);
        assert.ok(err.errors.length > 0);
        return true;
      }
    );
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

test("runAssemblyLinePipeline: targeted single-ticket mode runs only requested ticket", async () => {
  const repoDir = setupRepoWithPrereqs("single-ticket-feature");

  try {
    addTicket(repoDir, "single-ticket-feature", "01", "Ticket One");
    addTicket(repoDir, "single-ticket-feature", "02", "Ticket Two", "01");

    const executedTicketIds: string[] = [];

    const result = await runAssemblyLinePipeline({
      workspaceDir: repoDir,
      featureSlug: "single-ticket-feature",
      issueId: "01",
      push: false,
      plannerRunner: async ({ ticket }) => {
        const id = typeof ticket === "string" ? ticket : ticket.id;
        executedTicketIds.push(id);
        return { plan: mockPlan, messages: [] };
      },
      coderRunner: async () => {
        fs.writeFileSync(path.join(repoDir, "output.txt"), "ticket 1 done", "utf-8");
        return { summary: "Implemented", messages: [] };
      },
      verifierRunner: async () => ({
        passed: true,
        totalCommands: 1,
        passedCommands: 1,
        failedCommands: 0,
        results: [],
        summary: "PASSED",
        durationMs: 10,
      }),
      reviewerRunner: async () => ({ verdict: mockPassingReview, messages: [] }),
    });

    assert.equal(result.executedTickets.length, 1);
    assert.equal(result.executedTickets[0].ticketId, "01");
    assert.equal(result.executedTickets[0].status, "resolved");
    assert.deepEqual(executedTicketIds, ["01"]);
    assert.equal(result.branch, "factory/single-ticket-feature");
    assert.equal(result.haltedOnError, false);
  } finally {
    fs.rmSync(repoDir, { recursive: true, force: true });
  }
});

test("runAssemblyLinePipeline: Autonomous Feature Batch sequentially resolves frontier tickets", async () => {
  const repoDir = setupRepoWithPrereqs("batch-feature");

  try {
    addTicket(repoDir, "batch-feature", "01", "Ticket One");
    addTicket(repoDir, "batch-feature", "02", "Ticket Two", "01");

    const executedOrder: string[] = [];

    const result = await runAssemblyLinePipeline({
      workspaceDir: repoDir,
      featureSlug: "batch-feature",
      push: false,
      plannerRunner: async ({ ticket }) => {
        const id = typeof ticket === "string" ? ticket : ticket.id;
        executedOrder.push(id);
        return { plan: mockPlan, messages: [] };
      },
      coderRunner: async ({ ticket }) => {
        const id = typeof ticket === "string" ? ticket : ticket.id;
        fs.writeFileSync(path.join(repoDir, `file-${id}.txt`), `done ${id}`, "utf-8");
        return { summary: "Done", messages: [] };
      },
      verifierRunner: async () => ({
        passed: true,
        totalCommands: 1,
        passedCommands: 1,
        failedCommands: 0,
        results: [],
        summary: "PASSED",
        durationMs: 10,
      }),
      reviewerRunner: async () => ({ verdict: mockPassingReview, messages: [] }),
    });

    assert.equal(result.executedTickets.length, 2);
    assert.deepEqual(executedOrder, ["01", "02"]);
    assert.equal(result.allResolved, true);
    assert.equal(result.haltedOnError, false);

    // Both tickets should be resolved on disk
    const t1 = fs.readFileSync(path.join(repoDir, ".scratch", "batch-feature", "issues", "01-ticket-one.md"), "utf-8");
    const t2 = fs.readFileSync(path.join(repoDir, ".scratch", "batch-feature", "issues", "02-ticket-two.md"), "utf-8");
    assert.match(t1, /\*{0,2}Status(?::\*{0,2}|\*{0,2}:)\s*resolved/i);
    assert.match(t2, /\*{0,2}Status(?::\*{0,2}|\*{0,2}:)\s*resolved/i);
  } finally {
    fs.rmSync(repoDir, { recursive: true, force: true });
  }
});

test("runAssemblyLinePipeline: Autonomous Feature Batch halts immediately (fail-fast) when ticket fails and marks ready-for-human", async () => {
  const repoDir = setupRepoWithPrereqs("fail-fast-feature");

  try {
    addTicket(repoDir, "fail-fast-feature", "01", "Broken Ticket");
    addTicket(repoDir, "fail-fast-feature", "02", "Dependent Ticket", "01");

    const executedOrder: string[] = [];

    const result = await runAssemblyLinePipeline({
      workspaceDir: repoDir,
      featureSlug: "fail-fast-feature",
      maxRetries: 2,
      push: false,
      plannerRunner: async ({ ticket }) => {
        const id = typeof ticket === "string" ? ticket : ticket.id;
        executedOrder.push(id);
        return { plan: mockPlan, messages: [] };
      },
      coderRunner: async () => {
        fs.writeFileSync(path.join(repoDir, "broken.txt"), "failed code", "utf-8");
        return { summary: "Tried to fix", messages: [] };
      },
      verifierRunner: async () => ({
        passed: false,
        totalCommands: 1,
        passedCommands: 0,
        failedCommands: 1,
        results: [],
        summary: "SyntaxError: tests failed",
        durationMs: 10,
      }),
      reviewerRunner: async () => ({ verdict: mockPassingReview, messages: [] }),
    });

    // Batch halted immediately on ticket 01 failure!
    assert.equal(result.haltedOnError, true);
    assert.equal(result.allResolved, false);
    assert.deepEqual(executedOrder, ["01"]); // Ticket 02 was never run!
    assert.equal(result.executedTickets.length, 1);
    assert.equal(result.executedTickets[0].status, "ready-for-human");

    // Ticket 01 marked ready-for-human on disk
    const t1 = fs.readFileSync(path.join(repoDir, ".scratch", "fail-fast-feature", "issues", "01-broken-ticket.md"), "utf-8");
    assert.match(t1, /\*{0,2}Status(?::\*{0,2}|\*{0,2}:)\s*ready-for-human/i);

    // Ticket 02 remains ready-for-agent
    const t2 = fs.readFileSync(path.join(repoDir, ".scratch", "fail-fast-feature", "issues", "02-dependent-ticket.md"), "utf-8");
    assert.match(t2, /\*{0,2}Status(?::\*{0,2}|\*{0,2}:)\s*ready-for-agent/i);
  } finally {
    fs.rmSync(repoDir, { recursive: true, force: true });
  }
});

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

    const result = await runAssemblyLinePipeline({
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
    const result = await runAssemblyLinePipeline({
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
  } finally {
    fs.rmSync(repoDir, { recursive: true, force: true });
  }
});
