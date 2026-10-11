import React from "react";
import { renderHook, waitFor, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  studioQueryKeys,
  useChatMessagesQuery,
  useClearChatMessagesMutation,
  useStudioIssuesQuery,
  useDispatchStudioMutation,
} from "./useStudioQueries";
import * as api from "../api";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    fetchChatMessages: vi.fn(),
    clearChatMessages: vi.fn(),
    fetchIssues: vi.fn(),
    dispatchStudio: vi.fn(),
  };
});

describe("useStudioQueries - Chat Messages", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
  });

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  it("defines studioQueryKeys.messages(repo)", () => {
    expect(studioQueryKeys.messages("my-app")).toEqual(["studio", "messages", "my-app"]);
  });

  it("fetches chat messages via useChatMessagesQuery", async () => {
    const mockData = {
      repo: "my-app",
      messages: [
        {
          id: "m-1",
          repo: "my-app",
          role: "user" as const,
          content: "Hello",
          created_at: 1000,
        },
      ],
    };
    vi.mocked(api.fetchChatMessages).mockResolvedValue(mockData);

    const { result } = renderHook(() => useChatMessagesQuery("my-app"), { wrapper });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(api.fetchChatMessages).toHaveBeenCalledWith("my-app");
    expect(result.current.data).toEqual(mockData);
  });

  it("clears chat messages and updates query cache via useClearChatMessagesMutation", async () => {
    vi.mocked(api.clearChatMessages).mockResolvedValue({
      repo: "my-app",
      deleted: 2,
      success: true,
    });

    // Populate initial cache
    queryClient.setQueryData(studioQueryKeys.messages("my-app"), {
      repo: "my-app",
      messages: [{ id: "m-1", repo: "my-app", role: "user", content: "old", created_at: 1000 }],
    });

    const { result } = renderHook(() => useClearChatMessagesMutation(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync("my-app");
    });

    expect(api.clearChatMessages).toHaveBeenCalledWith("my-app");
    expect(queryClient.getQueryData(studioQueryKeys.messages("my-app"))).toEqual({
      repo: "my-app",
      messages: [],
    });
  });

  it("defines studioQueryKeys.issues(repo)", () => {
    expect(studioQueryKeys.issues("my-app")).toEqual(["studio", "issues", "my-app"]);
  });

  it("fetches GitHub issues via useStudioIssuesQuery", async () => {
    const mockData = {
      repo: "my-app",
      issues: [
        {
          number: 1,
          title: "Setup auth",
          status: "ready-for-agent",
          state: "open",
          blocked_by: [],
          labels: ["factory:ready"],
        },
      ],
    };
    vi.mocked(api.fetchIssues).mockResolvedValue(mockData);

    const { result } = renderHook(() => useStudioIssuesQuery("my-app"), { wrapper });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(api.fetchIssues).toHaveBeenCalledWith("my-app", undefined, "all");
    expect(result.current.data).toEqual(mockData);
  });

  it("dispatches job and invalidates query caches via useDispatchStudioMutation", async () => {
    const mockJob = {
      id: "job-disp-1",
      repo: "my-app",
      status: "RUNNING" as const,
      stage: "CODER" as const,
      model: "deepseek-v4.1-flash",
      vm: false,
      dev: true,
      created_at: "2026-10-11T00:00:00Z",
      log_count: 0,
      event_count: 0,
    };
    const mockDispatchRes = {
      accepted: true,
      job: mockJob,
      issue_number: 1,
      milestone_slug: "v1-app",
      branch: "factory/v1-app",
      target_branch: "factory/v1-app",
      preview_url: "https://sandbox-preview.modal.host",
      stage: "CODER",
    };
    vi.mocked(api.dispatchStudio).mockResolvedValue(mockDispatchRes);

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useDispatchStudioMutation(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        repo: "my-app",
        issue_number: 1,
        milestone_slug: "v1-app",
      });
    });

    expect(api.dispatchStudio).toHaveBeenCalledWith({
      repo: "my-app",
      issue_number: 1,
      milestone_slug: "v1-app",
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: studioQueryKeys.issues("my-app") });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: studioQueryKeys.messages("my-app") });
  });
});
