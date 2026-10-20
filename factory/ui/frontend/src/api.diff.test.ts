import { describe, it, expect, vi, beforeEach } from "vitest";
import { fetchRepoDiff } from "./api";

describe("fetchRepoDiff", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches working tree diff successfully", async () => {
    const mockDiffResponse = {
      repo: "my-repo",
      branch: "main",
      base: "main",
      scope: "working_tree",
      source: "sandbox",
      summary: { total_files: 1, additions: 2, deletions: 1 },
      files: [
        {
          path: "src/index.ts",
          status: "modified",
          additions: 2,
          deletions: 1,
          patch: "@@ -1,3 +1,4 @@\n-old\n+new 1\n+new 2\n",
        },
      ],
      clean: false,
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue(mockDiffResponse),
    } as any);

    const result = await fetchRepoDiff("my-repo", "working_tree");

    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/repos/my-repo/diff?scope=working_tree"
    );
    expect(result.summary.total_files).toBe(1);
    expect(result.files[0].path).toBe("src/index.ts");
    expect(result.clean).toBe(false);
  });

  it("fetches branch diff with branch and base query params", async () => {
    const mockDiffResponse = {
      repo: "my-repo",
      branch: "feature/login",
      base: "main",
      scope: "branch",
      source: "github",
      summary: { total_files: 0, additions: 0, deletions: 0 },
      files: [],
      clean: true,
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue(mockDiffResponse),
    } as any);

    const result = await fetchRepoDiff("my-repo", "branch", "feature/login", "main");

    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/repos/my-repo/diff?scope=branch&branch=feature%2Flogin&base=main"
    );
    expect(result.clean).toBe(true);
    expect(result.scope).toBe("branch");
  });

  it("throws error when endpoint responds with non-ok status", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      statusText: "Internal Server Error",
      json: vi.fn().mockResolvedValue({ detail: "Git diff execution failed" }),
    } as any);

    await expect(fetchRepoDiff("my-repo")).rejects.toThrow("Git diff execution failed");
  });
});
