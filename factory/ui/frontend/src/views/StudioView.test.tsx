import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { StudioView } from "./StudioView";

const mockRepos = [
  { name: "cool-app", is_tanstack_compatible: true },
  { name: "test-app", is_tanstack_compatible: false },
];

describe("StudioView", () => {
  it("renders repo select, prompt input, send button and live preview", () => {
    render(
      <StudioView
        repos={mockRepos}
        selectedRepo="cool-app"
        onSelectRepo={vi.fn()}
        onCreateRepo={vi.fn()}
        activeJob={null}
        messages={[]}
        onSendPrompt={vi.fn()}
        onCancelJob={vi.fn()}
        onSwitchToConsole={vi.fn()}
      />
    );

    expect(screen.getByPlaceholderText(/Describe what you want to build/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Send/i })).toBeInTheDocument();
    expect(screen.getByText("New App")).toBeInTheDocument();
  });

  it("handles prompt submission", () => {
    const handleSend = vi.fn();
    render(
      <StudioView
        repos={mockRepos}
        selectedRepo="cool-app"
        onSelectRepo={vi.fn()}
        onCreateRepo={vi.fn()}
        activeJob={null}
        messages={[]}
        onSendPrompt={handleSend}
        onCancelJob={vi.fn()}
        onSwitchToConsole={vi.fn()}
      />
    );

    const input = screen.getByPlaceholderText(/Describe what you want to build/i);
    fireEvent.change(input, { target: { value: "Add a dark mode toggle" } });

    const sendBtn = screen.getByRole("button", { name: /Send/i });
    fireEvent.click(sendBtn);

    expect(handleSend).toHaveBeenCalledWith("Add a dark mode toggle");
  });

  it("renders refusal card when intent guard rejects prompt", () => {
    const messages = [
      {
        id: "m-1",
        role: "assistant" as const,
        timestamp: Date.now(),
        refusal: {
          message: "Request cannot be processed because it falls outside frontend scope.",
          reason: "Out-of-scope backend infrastructure modification",
          category: "out_of_scope",
        },
      },
    ];

    render(
      <StudioView
        repos={mockRepos}
        selectedRepo="cool-app"
        onSelectRepo={vi.fn()}
        onCreateRepo={vi.fn()}
        activeJob={null}
        messages={messages}
        onSendPrompt={vi.fn()}
        onCancelJob={vi.fn()}
        onSwitchToConsole={vi.fn()}
      />
    );

    expect(screen.getByText(/Request cannot be processed/i)).toBeInTheDocument();
    expect(screen.getByText(/Out-of-scope backend infrastructure modification/i)).toBeInTheDocument();
  });

  it("renders 'Preview App' button in top control bar next to repo selector and triggers onLaunchPreview", () => {
    const handleLaunch = vi.fn();
    render(
      <StudioView
        repos={mockRepos}
        selectedRepo="cool-app"
        onSelectRepo={vi.fn()}
        onCreateRepo={vi.fn()}
        activeJob={null}
        messages={[]}
        onSendPrompt={vi.fn()}
        onCancelJob={vi.fn()}
        onSwitchToConsole={vi.fn()}
        onLaunchPreview={handleLaunch}
      />
    );

    const previewBtn = screen.getByTestId("preview-app-btn");
    expect(previewBtn).toBeInTheDocument();
    expect(previewBtn).toHaveTextContent(/Preview App/i);

    fireEvent.click(previewBtn);
    expect(handleLaunch).toHaveBeenCalledTimes(1);
  });
});

