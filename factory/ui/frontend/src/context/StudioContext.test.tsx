import { renderHook } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import React from "react";
import { StudioProvider, useStudio, StudioContextValue } from "./StudioContext";

describe("StudioContext", () => {
  it("throws an error when useStudio is used outside of StudioProvider", () => {
    expect(() => {
      renderHook(() => useStudio());
    }).toThrowError(/useStudio must be used within a StudioProvider/);
  });

  it("provides studio state and handlers to consumer components", () => {
    const mockValue: StudioContextValue = {
      repos: [{ name: "test-repo", is_tanstack_compatible: true }],
      selectedRepo: "test-repo",
      onSelectRepo: () => {},
      onCreateRepo: async () => {},
      activeJob: null,
      messages: [],
      onSendPrompt: () => {},
      onCancelJob: () => {},
      previewState: {
        repo: "test-repo",
        status: "SERVING",
        branch: "main",
        preview_url: "https://preview.modal.host",
        logs: [],
        error_message: null,
      },
    };

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <StudioProvider value={mockValue}>{children}</StudioProvider>
    );

    const { result } = renderHook(() => useStudio(), { wrapper });

    expect(result.current.selectedRepo).toBe("test-repo");
    expect(result.current.repos).toHaveLength(1);
    expect(result.current.previewState?.status).toBe("SERVING");
  });
});
