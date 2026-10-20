import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { ActivityDrawer } from "./ActivityDrawer";
import { Job } from "../types";
import { MockWebSocket } from "../test/setup";

describe("ActivityDrawer - Interactive Terminal Integration", () => {
  const originalWebSocket = window.WebSocket;

  beforeEach(() => {
    MockWebSocket.instances = [];
    (window as any).WebSocket = MockWebSocket as any;
  });

  afterEach(() => {
    window.WebSocket = originalWebSocket;
    vi.restoreAllMocks();
  });

  it("renders the Interactive Terminal tab button in drawer tab bar", () => {
    render(
      <ActivityDrawer
        isOpen={true}
        onClose={vi.fn()}
        selectedRepo="software-factory-09-test/my-app"
      />
    );

    const terminalTabBtn = screen.getByTestId("btn-drawer-tab-terminal");
    expect(terminalTabBtn).toBeInTheDocument();
    expect(terminalTabBtn).toHaveTextContent(/Interactive Terminal/i);
  });

  it("activates the Interactive Terminal tab on button click and mounts terminal container", () => {
    render(
      <ActivityDrawer
        isOpen={true}
        onClose={vi.fn()}
        selectedRepo="software-factory-09-test/my-app"
      />
    );

    const terminalTabBtn = screen.getByTestId("btn-drawer-tab-terminal");
    fireEvent.click(terminalTabBtn);

    expect(screen.getByTestId("interactive-terminal-container")).toBeInTheDocument();
    expect(screen.getByTestId("terminal-repo-badge")).toHaveTextContent("/root/my-app");
    expect(MockWebSocket.instances.length).toBe(1);
    expect(MockWebSocket.instances[0].url).toContain("/api/repos/my-app/terminal/ws");
  });

  it("opens directly to Interactive Terminal tab when initialTab is terminal or interactive_terminal", () => {
    render(
      <ActivityDrawer
        isOpen={true}
        onClose={vi.fn()}
        selectedRepo="software-factory-09-test/my-app"
        initialTab="terminal"
      />
    );

    expect(screen.getByTestId("interactive-terminal-container")).toBeInTheDocument();
  });

  it("displays pipeline warning badge when an Assembly Line Pipeline job is RUNNING", () => {
    const runningJobs: Job[] = [
      {
        id: "job-123",
        repo: "software-factory-09-test/my-app",
        status: "RUNNING",
        stage: "BUILD",
        model: "gemini",
        vm: true,
        dev: true,
        created_at: new Date().toISOString(),
        log_count: 0,
        event_count: 0,
      },
    ];

    render(
      <ActivityDrawer
        isOpen={true}
        onClose={vi.fn()}
        selectedRepo="software-factory-09-test/my-app"
        initialTab="terminal"
        jobs={runningJobs}
      />
    );

    expect(screen.getByTestId("terminal-pipeline-warning-badge")).toBeInTheDocument();
    expect(screen.getByTestId("terminal-pipeline-warning-badge")).toHaveTextContent(/Pipeline job running/i);
  });

  it("does not display pipeline warning badge when jobs are finished", () => {
    const finishedJobs: Job[] = [
      {
        id: "job-123",
        repo: "software-factory-09-test/my-app",
        status: "SUCCESS",
        stage: "COMPLETE",
        model: "gemini",
        vm: true,
        dev: true,
        created_at: new Date().toISOString(),
        log_count: 0,
        event_count: 0,
      },
    ];

    render(
      <ActivityDrawer
        isOpen={true}
        onClose={vi.fn()}
        selectedRepo="software-factory-09-test/my-app"
        initialTab="terminal"
        jobs={finishedJobs}
      />
    );

    expect(screen.queryByTestId("terminal-pipeline-warning-badge")).toBeNull();
  });

  it("closes the WebSocket connection when the drawer is closed", () => {
    const { rerender } = render(
      <ActivityDrawer
        isOpen={true}
        onClose={vi.fn()}
        selectedRepo="software-factory-09-test/my-app"
        initialTab="terminal"
      />
    );

    expect(MockWebSocket.instances.length).toBe(1);
    const ws = MockWebSocket.instances[0];
    expect(ws.closed).toBe(false);

    rerender(
      <ActivityDrawer
        isOpen={false}
        onClose={vi.fn()}
        selectedRepo="software-factory-09-test/my-app"
        initialTab="terminal"
      />
    );

    expect(ws.closed).toBe(true);
  });
});
