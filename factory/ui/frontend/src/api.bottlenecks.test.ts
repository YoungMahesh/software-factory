import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { fetchRepoBottlenecks } from "./api";

describe("api: fetchRepoBottlenecks", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("fetches repo bottlenecks successfully", async () => {
    const mockData = {
      repo: "my-repo",
      bottlenecks: [
        {
          command: "pnpm test",
          category: "Test Suite",
          stage: "VERIFIER",
          count: 3,
          total_duration_ms: 1200,
          avg_duration_ms: 400.0,
          max_duration_ms: 500,
        },
      ],
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockData,
    } as Response);

    const result = await fetchRepoBottlenecks("my-repo");

    expect(global.fetch).toHaveBeenCalledWith("/api/repos/my-repo/bottlenecks");
    expect(result).toEqual(mockData);
  });

  it("includes limit query parameter when specified", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ repo: "my-repo", bottlenecks: [] }),
    } as Response);

    await fetchRepoBottlenecks("my-repo", 10);

    expect(global.fetch).toHaveBeenCalledWith("/api/repos/my-repo/bottlenecks?limit=10");
  });

  it("throws an error when API request fails", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      statusText: "Bad Request",
      json: async () => ({ detail: "Repository name is required." }),
    } as Response);

    await expect(fetchRepoBottlenecks("")).rejects.toThrow(
      "Repository name is required."
    );
  });
});
