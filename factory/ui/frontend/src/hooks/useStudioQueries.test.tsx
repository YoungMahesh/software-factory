import React from "react";
import { renderHook, waitFor, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  studioQueryKeys,
  useChatMessagesQuery,
  useClearChatMessagesMutation,
} from "./useStudioQueries";
import * as api from "../api";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    fetchChatMessages: vi.fn(),
    clearChatMessages: vi.fn(),
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
});
