import test from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import { GitHubClient, type GitHubMilestone, type GitHubIssue } from "../github.ts";
import { GitHubIssueTracker, parseGitHubBlockedBy } from "./github-tracker.ts";

test("parseGitHubBlockedBy: parses various Blocked by formats", () => {
  assert.deepEqual(parseGitHubBlockedBy("Blocked by: #12"), ["12"]);
  assert.deepEqual(parseGitHubBlockedBy("**Blocked by:** #12, #15"), ["12", "15"]);
  assert.deepEqual(parseGitHubBlockedBy("Blocked by: #101, #102."), ["101", "102"]);
  assert.deepEqual(parseGitHubBlockedBy("Blocked by: None"), []);
  assert.deepEqual(parseGitHubBlockedBy("Blocked by: None (can start immediately)"), []);
  assert.deepEqual(parseGitHubBlockedBy(""), []);
  assert.deepEqual(parseGitHubBlockedBy("No blockers mentioned"), []);
});

test("GitHubIssueTracker: retrieves feature spec from milestone description", async () => {
  const milestone: GitHubMilestone = {
    id: 1,
    number: 5,
    title: "auth-feature",
    description: "## Auth Feature Spec\nRequirements go here.",
    state: "open",
    open_issues: 2,
    closed_issues: 0,
  };

  const client = new GitHubClient({
    token: "tok",
    owner: "org",
    repo: "repo",
    fetch: async (input) => {
      const url = String(input);
      if (url.includes("/milestones")) {
        return new Response(JSON.stringify([milestone]), { status: 200 });
      }
      return new Response("Not found", { status: 404 });
    },
  });

  const tracker = new GitHubIssueTracker({ client });
  const spec = await tracker.getFeatureSpec("/workspace", "auth-feature");
  assert.equal(spec, "## Auth Feature Spec\nRequirements go here.");
});

test("GitHubIssueTracker: parses tickets and computes frontier based on Blocked by dependencies", async () => {
  const milestone: GitHubMilestone = {
    id: 1,
    number: 5,
    title: "auth-feature",
    description: "Spec",
    state: "open",
    open_issues: 3,
    closed_issues: 0,
  };

  const issues: GitHubIssue[] = [
    {
      id: 101,
      number: 1,
      title: "Set up auth schema",
      body: "Blocked by: None\n\nCreate tables.",
      state: "open",
      labels: [{ name: "factory:ready" }],
    },
    {
      id: 102,
      number: 2,
      title: "Implement login endpoint",
      body: "Blocked by: #1\n\nBuild login handler.",
      state: "open",
      labels: [{ name: "factory:ready" }],
    },
    {
      id: 103,
      number: 3,
      title: "Write documentation",
      body: "Blocked by: #1, #2\n\nDocument auth.",
      state: "open",
      labels: [],
    },
  ];

  const client = new GitHubClient({
    token: "tok",
    owner: "org",
    repo: "repo",
    fetch: async (input) => {
      const url = String(input);
      if (url.includes("/milestones")) {
        return new Response(JSON.stringify([milestone]), { status: 200 });
      }
      if (url.includes("/issues?milestone=5")) {
        return new Response(JSON.stringify(issues), { status: 200 });
      }
      return new Response("Not found", { status: 404 });
    },
  });

  const tracker = new GitHubIssueTracker({ client });
  const tickets = await tracker.getTickets("/workspace", "auth-feature");
  assert.equal(tickets.length, 3);
  assert.equal(tickets[0].id, "1");
  assert.equal(tickets[0].status, "ready-for-agent");
  assert.deepEqual(tickets[1].blockedBy, ["1"]);
  assert.deepEqual(tickets[2].blockedBy, ["1", "2"]);

  // Frontier initially only has ticket 1
  const frontier = await tracker.getFrontierTickets("/workspace", "auth-feature");
  assert.equal(frontier.length, 1);
  assert.equal(frontier[0].id, "1");
});

test("GitHubIssueTracker: claim, resolve, and escalate update issue labels and post audit comments", async () => {
  const milestone: GitHubMilestone = {
    id: 1,
    number: 5,
    title: "auth-feature",
    description: "Spec",
    state: "open",
    open_issues: 1,
    closed_issues: 0,
  };

  const currentLabels = new Set<string>(["factory:ready"]);
  const comments: string[] = [];

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
      if (url.includes("/issues?milestone=5")) {
        return new Response(
          JSON.stringify([
            {
              id: 101,
              number: 42,
              title: "Ticket 42",
              body: "Blocked by: None",
              state: "open",
              labels: Array.from(currentLabels).map((name) => ({ name })),
            },
          ]),
          { status: 200 }
        );
      }
      if (url.includes("/issues/42/comments") && method === "POST") {
        const body = JSON.parse(String(init?.body));
        comments.push(body.body);
        return new Response(JSON.stringify({ id: 1, body: body.body }), { status: 201 });
      }
      if (url.includes("/issues/42") && method === "GET") {
        return new Response(
          JSON.stringify({
            id: 101,
            number: 42,
            title: "Ticket 42",
            body: "Blocked by: None",
            state: "open",
            labels: Array.from(currentLabels).map((name) => ({ name })),
          }),
          { status: 200 }
        );
      }
      if (url.includes("/issues/42") && method === "PATCH") {
        const body = JSON.parse(String(init?.body));
        if (body.labels) {
          currentLabels.clear();
          for (const l of body.labels) currentLabels.add(l);
        }
        return new Response(JSON.stringify({ id: 101, number: 42, labels: Array.from(currentLabels) }), {
          status: 200,
        });
      }
      return new Response("Not found", { status: 404 });
    },
  });

  const tracker = new GitHubIssueTracker({ client });
  const tickets = await tracker.getTickets("/workspace", "auth-feature");
  const ticket = tickets[0];

  // 1. Claim ticket
  await tracker.claimTicket(ticket, { branch: "factory/auth-feature" });
  assert.equal(ticket.status, "claimed");
  assert.ok(currentLabels.has("factory:claimed"));
  assert.ok(!currentLabels.has("factory:ready"));

  // 2. Resolve ticket
  await tracker.resolveTicket(ticket, {
    branch: "factory/auth-feature",
    commitSha: "deadbeef0123",
    auditSummary: "Verification passed with flying colors.",
  });
  assert.equal(ticket.status, "resolved");
  assert.ok(currentLabels.has("factory:resolved"));
  assert.ok(!currentLabels.has("factory:claimed"));
  assert.equal(comments.length, 1);
  assert.ok(comments[0].includes("Quality Gate Audit"));
  assert.ok(comments[0].includes("deadbeef0123"));

  // 3. Escalate ticket
  await tracker.escalateTicket(ticket, {
    branch: "factory/auth-feature",
    failureDiagnostics: "Max retries exhausted in self-correction loop.",
  });
  assert.equal(ticket.status, "ready-for-human");
  assert.ok(currentLabels.has("factory:ready-for-human"));
  assert.ok(!currentLabels.has("factory:resolved"));
  assert.equal(comments.length, 2);
  assert.ok(comments[1].includes("Failure Diagnostics"));
});

test("GitHubIssueTracker: Delivery Gate lifecycle (create draft PR -> incremental update -> alert on failure -> finalize)", async () => {
  let createdPrPayload: any = null;
  let updatedPrPayload: any = null;
  const prComments: string[] = [];
  const currentPr = {
    id: 501,
    number: 77,
    title: "feat(feature-alpha): implement feature-alpha",
    body: "",
    state: "open",
    draft: true,
    html_url: "https://github.com/org/repo/pull/77",
  };

  const client = new GitHubClient({
    token: "tok",
    owner: "org",
    repo: "repo",
    fetch: async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";

      if (url.includes("/milestones")) {
        return new Response(JSON.stringify([{ id: 1, number: 1, title: "feature-alpha", description: "Alpha Spec", state: "open" }]), { status: 200 });
      }
      if (url.includes("/pulls") && method === "GET") {
        if (createdPrPayload) {
          return new Response(JSON.stringify([currentPr]), { status: 200 });
        }
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (url.includes("/pulls") && method === "POST") {
        createdPrPayload = JSON.parse(String(init?.body));
        currentPr.title = createdPrPayload.title;
        currentPr.body = createdPrPayload.body;
        currentPr.draft = createdPrPayload.draft;
        return new Response(JSON.stringify(currentPr), { status: 201 });
      }
      if (url.includes("/pulls/77") && method === "PATCH") {
        updatedPrPayload = JSON.parse(String(init?.body));
        if (updatedPrPayload.body !== undefined) currentPr.body = updatedPrPayload.body;
        if (updatedPrPayload.draft !== undefined) currentPr.draft = updatedPrPayload.draft;
        return new Response(JSON.stringify(currentPr), { status: 200 });
      }
      if (url.includes("/issues/77/comments") && method === "POST") {
        const body = JSON.parse(String(init?.body));
        prComments.push(body.body);
        return new Response(JSON.stringify({ id: 1, body: body.body }), { status: 201 });
      }
      return new Response("Not found", { status: 404 });
    },
  });

  const tracker = new GitHubIssueTracker({ client });
  const ticket1 = {
    id: "1",
    number: 1,
    slug: "t1",
    title: "Ticket One",
    filePath: "",
    status: "resolved" as const,
    blockedBy: [],
  };
  const ticket2 = {
    id: "2",
    number: 2,
    slug: "t2",
    title: "Ticket Two",
    filePath: "",
    status: "resolved" as const,
    blockedBy: [],
  };

  // 1. Initialize delivery gate on first resolved ticket (ticket1)
  const initResult = await tracker.initializeDeliveryGate({
    workspaceDir: "/workspace",
    featureSlug: "feature-alpha",
    branch: "factory/feature-alpha",
    ticket: ticket1,
  });

  assert.ok(initResult);
  assert.equal(initResult?.pullRequestNumber, 77);
  assert.equal(initResult?.branch, "factory/feature-alpha");
  assert.ok(createdPrPayload);
  assert.equal(createdPrPayload.draft, true);
  assert.equal(createdPrPayload.base, "main");
  assert.equal(createdPrPayload.head, "factory/feature-alpha");
  assert.ok(createdPrPayload.body.includes("Fixes #1: Ticket One"));

  // 2. Incremental update when ticket2 resolves
  await tracker.updateDeliveryGate({
    workspaceDir: "/workspace",
    featureSlug: "feature-alpha",
    branch: "factory/feature-alpha",
    ticket: ticket2,
    status: "resolved",
  });

  assert.ok(currentPr.body.includes("Fixes #1: Ticket One"));
  assert.ok(currentPr.body.includes("Fixes #2: Ticket Two"));

  // 3. Update delivery gate with alert on ticket failure
  const failingTicket = {
    id: "3",
    number: 3,
    slug: "t3",
    title: "Broken Ticket",
    filePath: "",
    status: "ready-for-human" as const,
    blockedBy: [],
  };
  await tracker.updateDeliveryGate({
    workspaceDir: "/workspace",
    featureSlug: "feature-alpha",
    branch: "factory/feature-alpha",
    ticket: failingTicket,
    status: "ready-for-human",
    diagnostics: "Compile error in service.ts",
  });

  assert.ok(currentPr.body.includes("Software Factory Alert"));
  assert.ok(currentPr.body.includes("Broken Ticket"));
  assert.equal(prComments.length, 1);
  assert.ok(prComments[0].includes("Broken Ticket"));
  assert.ok(prComments[0].includes("Compile error in service.ts"));

  // 4. Finalize delivery gate converts PR to ready-for-review and posts summary table
  const finalizeResult = await tracker.finalizeDeliveryGate({
    workspaceDir: "/workspace",
    featureSlug: "feature-alpha",
    branch: "factory/feature-alpha",
    tickets: [ticket1, ticket2],
    summary: "| Ticket | Status |\n| 1 | Resolved |\n| 2 | Resolved |",
  });

  assert.ok(finalizeResult);
  assert.equal(finalizeResult?.readyForReview, true);
  assert.equal(currentPr.draft, false);
  assert.equal(prComments.length, 2);
  assert.ok(prComments[1].includes("| Ticket | Status |"));
});

test("GitHubIssueTracker: ad-hoc single issue dispatch operates on factory/issue-<id> without milestone", async () => {
  const issue = {
    id: 109,
    number: 99,
    title: "Fix null pointer in auth validator",
    body: "Blocked by: None\n\nFix the null pointer bug.",
    state: "open",
    labels: [{ name: "bug" }],
    html_url: "https://github.com/org/repo/issues/99",
  };

  let createdPrPayload: any = null;

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
      if (url.includes("/issues/99") && method === "GET") {
        return new Response(JSON.stringify(issue), { status: 200 });
      }
      if (url.includes("/pulls") && method === "POST") {
        createdPrPayload = JSON.parse(String(init?.body));
        return new Response(
          JSON.stringify({
            id: 999,
            number: 88,
            title: createdPrPayload.title,
            body: createdPrPayload.body,
            state: "open",
            draft: true,
            html_url: "https://github.com/org/repo/pull/88",
          }),
          { status: 201 }
        );
      }
      return new Response("Not found", { status: 404 });
    },
  });

  const tracker = new GitHubIssueTracker({ client });

  // 1. Preflight succeeds with single issue even without milestone
  // Mock CONTEXT.md in tmp dir
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "sf-single-issue-"));
  try {
    fs.writeFileSync(path.join(tmpDir, "CONTEXT.md"), "# Domain\n");
    const preflight = await tracker.validatePreflight(tmpDir, "issue-99", "99");
    assert.equal(preflight.valid, true);

    // 2. Spec returns issue body
    const spec = await tracker.getFeatureSpec(tmpDir, "issue-99", "99");
    assert.equal(spec, issue.body);

    // 3. Tickets returns single ticket
    const tickets = await tracker.getTickets(tmpDir, "issue-99", "99");
    assert.equal(tickets.length, 1);
    assert.equal(tickets[0].id, "99");
    assert.equal(tickets[0].title, "Fix null pointer in auth validator");

    // 4. Initialize delivery gate creates PR targeting main on factory/issue-99
    const initResult = await tracker.initializeDeliveryGate({
      workspaceDir: tmpDir,
      featureSlug: "issue-99",
      branch: "factory/issue-99",
      ticket: tickets[0],
    });
    assert.ok(initResult);
    assert.equal(initResult?.branch, "factory/issue-99");
    assert.equal(createdPrPayload.head, "factory/issue-99");
    assert.ok(createdPrPayload.title.includes("#99"));
    assert.ok(createdPrPayload.body.includes("Fixes #99"));
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});
