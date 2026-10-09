import test from "node:test";
import assert from "node:assert/strict";
import { GitHubClient, GitHubAuthError } from "./github.ts";

test("GitHubClient: authenticates via explicit token and repo options, setting standard headers", async () => {
  let capturedUrl = "";
  let capturedHeaders: Record<string, string> = {};

  const mockFetch: typeof globalThis.fetch = async (input, init) => {
    capturedUrl = String(input);
    const headers = init?.headers as any;
    if (headers instanceof Headers) {
      headers.forEach((val, key) => {
        capturedHeaders[key] = val;
      });
    } else if (headers) {
      capturedHeaders = { ...headers };
    }
    return new Response(JSON.stringify([{ id: 1, title: "v1.0" }]), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  const client = new GitHubClient({
    token: "ghp_secret123",
    owner: "software-factory-09-test",
    repo: "repo-horizon",
    fetch: mockFetch,
  });

  const milestones = await client.listMilestones();
  assert.equal(capturedUrl, "https://api.github.com/repos/software-factory-09-test/repo-horizon/milestones?state=open");
  assert.equal(capturedHeaders["Authorization"], "Bearer ghp_secret123");
  assert.equal(capturedHeaders["Accept"], "application/vnd.github+json");
  assert.equal(capturedHeaders["X-GitHub-Api-Version"], "2022-11-28");
  assert.equal(milestones.length, 1);
  assert.equal(milestones[0].title, "v1.0");
});

test("GitHubClient: resolves token and repo from environment variables", async () => {
  const origToken = process.env.GH_TOKEN;
  const origRepo = process.env.GH_REPO;
  try {
    process.env.GH_TOKEN = "env_token_abc";
    process.env.GH_REPO = "org-test/app-test";

    const client = new GitHubClient();
    assert.equal(client.token, "env_token_abc");
    assert.equal(client.owner, "org-test");
    assert.equal(client.repo, "app-test");
  } finally {
    process.env.GH_TOKEN = origToken;
    process.env.GH_REPO = origRepo;
  }
});

test("GitHubClient: getMilestone matches by title or slug", async () => {
  const mockFetch: typeof globalThis.fetch = async () => {
    return new Response(
      JSON.stringify([
        { id: 101, number: 1, title: "01-initial-feature", description: "First feature spec", state: "open" },
        { id: 102, number: 2, title: "Feature Two", description: "Second feature spec", state: "open" },
      ]),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  };

  const client = new GitHubClient({
    token: "tok",
    owner: "org",
    repo: "repo",
    fetch: mockFetch,
  });

  const found1 = await client.getMilestone("01-initial-feature");
  assert.ok(found1);
  assert.equal(found1?.number, 1);

  const found2 = await client.getMilestone("feature-two");
  assert.ok(found2);
  assert.equal(found2?.number, 2);

  const missing = await client.getMilestone("non-existent");
  assert.equal(missing, null);
});

test("GitHubClient: listIssuesForMilestone filters out pull requests", async () => {
  let requestedUrl = "";
  const mockFetch: typeof globalThis.fetch = async (input) => {
    requestedUrl = String(input);
    return new Response(
      JSON.stringify([
        {
          id: 11,
          number: 101,
          title: "Ticket 1",
          body: "Description",
          state: "open",
          labels: [{ name: "factory:ready" }],
        },
        {
          id: 12,
          number: 102,
          title: "PR 102",
          body: "Pull request body",
          state: "open",
          labels: [],
          pull_request: { url: "https://..." }, // GitHub API includes pull_request key for PRs in issues endpoint
        },
      ]),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  };

  const client = new GitHubClient({
    token: "tok",
    owner: "org",
    repo: "repo",
    fetch: mockFetch,
  });

  const issues = await client.listIssuesForMilestone(1);
  assert.ok(requestedUrl.includes("/issues?milestone=1&state=all"));
  assert.equal(issues.length, 1);
  assert.equal(issues[0].number, 101);
});

test("GitHubClient: addComment sends POST to /issues/{id}/comments", async () => {
  let capturedUrl = "";
  let capturedMethod = "";
  let capturedBody = "";

  const mockFetch: typeof globalThis.fetch = async (input, init) => {
    capturedUrl = String(input);
    capturedMethod = init?.method ?? "GET";
    capturedBody = String(init?.body ?? "");
    return new Response(JSON.stringify({ id: 999, body: "comment text" }), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    });
  };

  const client = new GitHubClient({
    token: "tok",
    owner: "org",
    repo: "repo",
    fetch: mockFetch,
  });

  await client.addComment(42, "Hello world comment");
  assert.ok(capturedUrl.endsWith("/repos/org/repo/issues/42/comments"));
  assert.equal(capturedMethod, "POST");
  assert.deepEqual(JSON.parse(capturedBody), { body: "Hello world comment" });
});

test("GitHubClient: updateIssue sends PATCH with labels or state", async () => {
  let capturedUrl = "";
  let capturedMethod = "";
  let capturedBody = "";

  const mockFetch: typeof globalThis.fetch = async (input, init) => {
    capturedUrl = String(input);
    capturedMethod = init?.method ?? "GET";
    capturedBody = String(init?.body ?? "");
    return new Response(JSON.stringify({ id: 42, number: 42, state: "closed", labels: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  const client = new GitHubClient({
    token: "tok",
    owner: "org",
    repo: "repo",
    fetch: mockFetch,
  });

  await client.updateIssue(42, { labels: ["factory:resolved"] });
  assert.ok(capturedUrl.endsWith("/repos/org/repo/issues/42"));
  assert.equal(capturedMethod, "PATCH");
  assert.deepEqual(JSON.parse(capturedBody), { labels: ["factory:resolved"] });
});

test("GitHubClient: throws GitHubApiError on non-ok HTTP responses", async () => {
  const mockFetch: typeof globalThis.fetch = async () => {
    return new Response(JSON.stringify({ message: "Bad credentials" }), {
      status: 401,
      statusText: "Unauthorized",
      headers: { "Content-Type": "application/json" },
    });
  };

  const client = new GitHubClient({
    token: "bad_tok",
    owner: "org",
    repo: "repo",
    fetch: mockFetch,
  });

  await assert.rejects(
    async () => {
      await client.listMilestones();
    },
    (err: any) => {
      assert.equal(err.name, "GitHubApiError");
      assert.equal(err.status, 401);
      assert.ok(err.message.includes("Bad credentials"));
      return true;
    }
  );
});

test("GitHubClient: createPullRequest and updatePullRequest send correct payload", async () => {
  let capturedUrl = "";
  let capturedMethod = "";
  let capturedBody = "";

  const mockFetch: typeof globalThis.fetch = async (input, init) => {
    capturedUrl = String(input);
    capturedMethod = init?.method ?? "GET";
    capturedBody = String(init?.body ?? "");
    return new Response(
      JSON.stringify({
        id: 501,
        number: 10,
        title: "feat: new feature",
        body: "PR body",
        state: "open",
        draft: true,
        html_url: "https://github.com/org/repo/pull/10",
      }),
      { status: 201, headers: { "Content-Type": "application/json" } }
    );
  };

  const client = new GitHubClient({
    token: "tok",
    owner: "org",
    repo: "repo",
    fetch: mockFetch,
  });

  const pr = await client.createPullRequest({
    title: "feat: new feature",
    body: "PR body",
    head: "factory/feature",
    base: "main",
    draft: true,
  });

  assert.ok(capturedUrl.endsWith("/repos/org/repo/pulls"));
  assert.equal(capturedMethod, "POST");
  assert.deepEqual(JSON.parse(capturedBody), {
    title: "feat: new feature",
    body: "PR body",
    head: "factory/feature",
    base: "main",
    draft: true,
  });
  assert.equal(pr.number, 10);
  assert.equal(pr.draft, true);

  // Update PR
  await client.updatePullRequest(10, { draft: false, body: "Updated body" });
  assert.ok(capturedUrl.endsWith("/repos/org/repo/pulls/10"));
  assert.equal(capturedMethod, "PATCH");
  assert.deepEqual(JSON.parse(capturedBody), {
    draft: false,
    body: "Updated body",
  });
});

test("GitHubClient: listPullRequests and getPullRequest send correct requests", async () => {
  let capturedUrl = "";

  const mockFetch: typeof globalThis.fetch = async (input) => {
    capturedUrl = String(input);
    if (capturedUrl.endsWith("/pulls/10")) {
      return new Response(
        JSON.stringify({
          id: 501,
          number: 10,
          title: "feat: test",
          body: "body",
          state: "open",
          draft: true,
          html_url: "https://github.com/org/repo/pull/10",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    return new Response(
      JSON.stringify([
        {
          id: 501,
          number: 10,
          title: "feat: test",
          body: "body",
          state: "open",
          draft: true,
          html_url: "https://github.com/org/repo/pull/10",
        },
      ]),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  };

  const client = new GitHubClient({
    token: "tok",
    owner: "org",
    repo: "repo",
    fetch: mockFetch,
  });

  const prs = await client.listPullRequests({ state: "open", head: "org:factory/feature" });
  assert.ok(capturedUrl.includes("/repos/org/repo/pulls?state=open&head=org%3Afactory%2Ffeature"));
  assert.equal(prs.length, 1);
  assert.equal(prs[0].number, 10);

  const singlePr = await client.getPullRequest(10);
  assert.ok(capturedUrl.endsWith("/repos/org/repo/pulls/10"));
  assert.equal(singlePr.number, 10);
});



