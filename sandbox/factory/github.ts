export class GitHubAuthError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "GitHubAuthError";
  }
}

export class GitHubApiError extends Error {
  public readonly status: number;
  public readonly responseBody?: any;

  constructor(message: string, status: number, responseBody?: any) {
    super(message);
    this.name = "GitHubApiError";
    this.status = status;
    this.responseBody = responseBody;
  }
}

export interface GitHubMilestone {
  id: number;
  number: number;
  title: string;
  description: string | null;
  state: "open" | "closed";
  open_issues: number;
  closed_issues: number;
}

export interface GitHubIssueLabel {
  id?: number;
  name: string;
  color?: string;
}

export interface GitHubIssue {
  id: number;
  number: number;
  title: string;
  body: string | null;
  state: "open" | "closed";
  labels: (string | GitHubIssueLabel)[];
  milestone?: GitHubMilestone | null;
  pull_request?: Record<string, any>;
  html_url?: string;
}

export interface GitHubPullRequest {
  id: number;
  node_id?: string;
  number: number;
  title: string;
  body: string | null;
  state: "open" | "closed";
  draft: boolean;
  html_url: string;
}

export interface GitHubClientOptions {
  token?: string;
  owner?: string;
  repo?: string;
  repoFullName?: string;
  apiBaseUrl?: string;
  fetch?: typeof globalThis.fetch;
}

export class GitHubClient {
  public readonly token: string;
  public readonly owner: string;
  public readonly repo: string;
  public readonly apiBaseUrl: string;
  private readonly customFetch?: typeof globalThis.fetch;

  constructor(options: GitHubClientOptions = {}) {
    const token = options.token ?? process.env.GH_TOKEN ?? process.env.GITHUB_TOKEN;
    if (!token || token.trim().length === 0) {
      throw new GitHubAuthError("Missing GitHub token. Ensure GH_TOKEN or GITHUB_TOKEN is set.");
    }
    this.token = token.trim();

    let owner = options.owner;
    let repo = options.repo;

    if (!owner || !repo) {
      const fullName = options.repoFullName ?? process.env.GH_REPO ?? process.env.GITHUB_REPOSITORY;
      if (fullName && fullName.includes("/")) {
        const parts = fullName.split("/");
        owner = owner ?? parts[0].trim();
        repo = repo ?? parts[1].trim();
      }
    }

    if (!owner || !repo) {
      throw new Error("Missing GitHub owner or repo. Pass owner/repo or set GH_REPO=owner/repo in environment.");
    }

    this.owner = owner;
    this.repo = repo;
    this.apiBaseUrl = (options.apiBaseUrl ?? "https://api.github.com").replace(/\/+$/, "");
    this.customFetch = options.fetch;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const fetchFn = this.customFetch ?? globalThis.fetch;
    const url = endpoint.startsWith("http") ? endpoint : `${this.apiBaseUrl}${endpoint}`;

    const headers: Record<string, string> = {
      Authorization: `Bearer ${this.token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "Modal-Software-Factory",
      ...(options.headers as Record<string, string>),
    };

    const response = await fetchFn(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      let bodyText = "";
      try {
        bodyText = await response.text();
      } catch {
        // ignore
      }
      let parsedBody: any;
      try {
        parsedBody = JSON.parse(bodyText);
      } catch {
        parsedBody = bodyText;
      }
      throw new GitHubApiError(
        `GitHub API error (${response.status} ${response.statusText}): ${parsedBody?.message ?? bodyText}`,
        response.status,
        parsedBody
      );
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return (await response.json()) as T;
  }

  public async listMilestones(state: "open" | "closed" | "all" = "open"): Promise<GitHubMilestone[]> {
    return this.request<GitHubMilestone[]>(
      `/repos/${this.owner}/${this.repo}/milestones?state=${state}`
    );
  }

  public async getMilestone(titleOrSlug: string): Promise<GitHubMilestone | null> {
    const milestones = await this.listMilestones("all");
    const normalizedTarget = titleOrSlug.trim().toLowerCase().replace(/[\s_]+/g, "-");

    const matched = milestones.find((m) => {
      const normalizedTitle = m.title.trim().toLowerCase().replace(/[\s_]+/g, "-");
      return (
        m.title.toLowerCase() === titleOrSlug.toLowerCase() ||
        normalizedTitle === normalizedTarget ||
        String(m.number) === titleOrSlug
      );
    });

    return matched ?? null;
  }

  public async listIssuesForMilestone(
    milestoneNumber: number,
    state: "open" | "closed" | "all" = "all"
  ): Promise<GitHubIssue[]> {
    const issues = await this.request<GitHubIssue[]>(
      `/repos/${this.owner}/${this.repo}/issues?milestone=${milestoneNumber}&state=${state}`
    );
    // GitHub issues endpoint includes pull requests; filter them out
    return issues.filter((item) => !item.pull_request);
  }

  public async getIssue(issueNumber: number): Promise<GitHubIssue> {
    return this.request<GitHubIssue>(`/repos/${this.owner}/${this.repo}/issues/${issueNumber}`);
  }

  public async addComment(issueNumber: number, body: string): Promise<{ id: number; body: string }> {
    return this.request<{ id: number; body: string }>(
      `/repos/${this.owner}/${this.repo}/issues/${issueNumber}/comments`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body }),
      }
    );
  }

  public async updateIssue(
    issueNumber: number,
    update: {
      title?: string;
      body?: string;
      state?: "open" | "closed";
      labels?: string[];
    }
  ): Promise<GitHubIssue> {
    return this.request<GitHubIssue>(`/repos/${this.owner}/${this.repo}/issues/${issueNumber}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(update),
    });
  }

  public async createPullRequest(options: {
    title: string;
    body: string;
    head: string;
    base: string;
    draft?: boolean;
  }): Promise<GitHubPullRequest> {
    return this.request<GitHubPullRequest>(`/repos/${this.owner}/${this.repo}/pulls`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(options),
    });
  }

  public async updatePullRequest(
    pullNumber: number,
    update: {
      title?: string;
      body?: string;
      state?: "open" | "closed";
      draft?: boolean;
    }
  ): Promise<GitHubPullRequest> {
    const res = await this.request<GitHubPullRequest>(`/repos/${this.owner}/${this.repo}/pulls/${pullNumber}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(update),
    });

    if (update.draft === false && res?.node_id) {
      try {
        await this.request<any>("/graphql", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query: `mutation($id: ID!) { markPullRequestReadyForReview(input: {pullRequestId: $id}) { pullRequest { id isDraft } } }`,
            variables: { id: res.node_id },
          }),
        });
        res.draft = false;
      } catch {
        // Fallback gracefully if GraphQL is not available or mocked
      }
    }

    return res;
  }

  public async listPullRequests(options?: {
    state?: "open" | "closed" | "all";
    head?: string;
    base?: string;
  }): Promise<GitHubPullRequest[]> {
    const params = new URLSearchParams();
    if (options?.state) params.set("state", options.state);
    if (options?.head) params.set("head", options.head);
    if (options?.base) params.set("base", options.base);
    const qs = params.toString() ? `?${params.toString()}` : "";
    return this.request<GitHubPullRequest[]>(`/repos/${this.owner}/${this.repo}/pulls${qs}`);
  }

  public async getPullRequest(pullNumber: number): Promise<GitHubPullRequest> {
    return this.request<GitHubPullRequest>(`/repos/${this.owner}/${this.repo}/pulls/${pullNumber}`);
  }
}


