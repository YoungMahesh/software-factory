import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { AppNavigation } from "./AppNavigation";
import { Job } from "../types";

describe("AppNavigation", () => {
  const dummyJob: Job = {
    id: "job-test-1",
    repo: "my-app",
    feature: "feature-test",
    issue: "1",
    model: "deepseek-v4.1-flash",
    vm: false,
    dev: true,
    status: "RUNNING",
    stage: "CODER",
    created_at: Date.now(),
    started_at: Date.now(),
    ended_at: null,
    exit_code: null,
    error_message: null,
    logs_count: 0,
  };

  it("renders navigation branding, repo pill, and Activity Drawer trigger button", () => {
    const onOpenDrawer = vi.fn();
    render(
      <AppNavigation
        activeJob={null}
        selectedRepo="my-app"
        onOpenDrawer={onOpenDrawer}
        failedCommandCount={0}
      />
    );

    expect(screen.getByText("Software Factory")).toBeInTheDocument();
    expect(screen.getByText("my-app")).toBeInTheDocument();
    expect(screen.getByTestId("nav-activity-drawer-btn")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Activity/i })).toBeInTheDocument();
  });

  it("renders coral error counter badge on Activity button when active job has failed commands", () => {
    const onOpenDrawer = vi.fn();
    render(
      <AppNavigation
        activeJob={dummyJob}
        selectedRepo="my-app"
        onOpenDrawer={onOpenDrawer}
        failedCommandCount={3}
      />
    );

    const badge = screen.getByTestId("nav-failed-commands-badge");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent("3");
    expect(badge.className).toContain("bg-coral");
    expect(badge.className).toContain("text-white");
  });

  it("completely omits coral error counter badge when zero commands failed", () => {
    const onOpenDrawer = vi.fn();
    render(
      <AppNavigation
        activeJob={dummyJob}
        selectedRepo="my-app"
        onOpenDrawer={onOpenDrawer}
        failedCommandCount={0}
      />
    );

    expect(screen.queryByTestId("nav-failed-commands-badge")).toBeNull();
  });

  it("completely omits coral error counter badge when no job is active", () => {
    const onOpenDrawer = vi.fn();
    render(
      <AppNavigation
        activeJob={null}
        selectedRepo="my-app"
        onOpenDrawer={onOpenDrawer}
        failedCommandCount={5}
      />
    );

    expect(screen.queryByTestId("nav-failed-commands-badge")).toBeNull();
  });

  it("routes directly to failed-commands tab when clicking Activity button with active failed commands", () => {
    const onOpenDrawer = vi.fn();
    render(
      <AppNavigation
        activeJob={dummyJob}
        selectedRepo="my-app"
        onOpenDrawer={onOpenDrawer}
        failedCommandCount={2}
      />
    );

    const btn = screen.getByTestId("nav-activity-drawer-btn");
    fireEvent.click(btn);

    expect(onOpenDrawer).toHaveBeenCalledWith(undefined, "failed-commands");
  });

  it("opens Activity Drawer preserving current tab when clicking Activity button with zero failed commands", () => {
    const onOpenDrawer = vi.fn();
    render(
      <AppNavigation
        activeJob={dummyJob}
        selectedRepo="my-app"
        onOpenDrawer={onOpenDrawer}
        failedCommandCount={0}
      />
    );

    const btn = screen.getByTestId("nav-activity-drawer-btn");
    fireEvent.click(btn);

    expect(onOpenDrawer).toHaveBeenCalledWith(undefined, undefined);
  });
});
