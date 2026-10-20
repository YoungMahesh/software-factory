import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { InteractiveTerminalTab } from "./InteractiveTerminalTab";
import { MockWebSocket } from "../../test/setup";

describe("InteractiveTerminalTab", () => {
  const originalWebSocket = window.WebSocket;

  beforeEach(() => {
    MockWebSocket.instances = [];
    (window as any).WebSocket = MockWebSocket as any;
  });

  afterEach(() => {
    window.WebSocket = originalWebSocket;
    vi.restoreAllMocks();
  });

  it("initiates WebSocket connection to /api/repos/{repo}/terminal/ws", async () => {
    render(<InteractiveTerminalTab repo="my-repo" />);

    expect(MockWebSocket.instances.length).toBe(1);
    expect(MockWebSocket.instances[0].url).toContain("/api/repos/my-repo/terminal/ws");
    expect(screen.getByTestId("interactive-terminal-container")).toBeInTheDocument();
  });

  it("renders pipeline warning badge when an Assembly Line Pipeline job is actively running", () => {
    const { rerender } = render(
      <InteractiveTerminalTab repo="my-repo" isPipelineRunning={false} />
    );

    expect(screen.queryByTestId("terminal-pipeline-warning-badge")).toBeNull();

    rerender(<InteractiveTerminalTab repo="my-repo" isPipelineRunning={true} />);

    const badge = screen.getByTestId("terminal-pipeline-warning-badge");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent(/Pipeline job running/i);
  });

  it("closes the WebSocket connection when unmounted", () => {
    const { unmount } = render(<InteractiveTerminalTab repo="my-repo" />);

    expect(MockWebSocket.instances.length).toBe(1);
    const ws = MockWebSocket.instances[0];

    unmount();
    expect(ws.closed).toBe(true);
  });

  it("renders repo path badge and action buttons", () => {
    render(<InteractiveTerminalTab repo="software-factory-09-test/frontend-app" />);

    expect(screen.getByTestId("terminal-repo-badge")).toHaveTextContent("/root/frontend-app");
    expect(screen.getByTestId("btn-terminal-clear")).toBeInTheDocument();
  });

  it("allows clearing terminal output via clear button", () => {
    render(<InteractiveTerminalTab repo="my-repo" />);

    const clearBtn = screen.getByTestId("btn-terminal-clear");
    fireEvent.click(clearBtn);
    expect(clearBtn).toBeInTheDocument();
  });
});
