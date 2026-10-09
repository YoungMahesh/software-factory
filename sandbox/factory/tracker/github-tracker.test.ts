import test from "node:test";
import assert from "node:assert/strict";
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
