import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { AppNavigation } from "./AppNavigation";
import { StudioContext } from "../context/StudioContext";
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

  it("renders navigation branding and Activity Drawer trigger button without static repo pill", () => {
    const onOpenDrawer = vi.fn();
    render(
      <AppNavigation
        activeJob={null}
        onOpenDrawer={onOpenDrawer}
        failedCommandCount={0}
      />
    );

    expect(screen.getByText("Software Factory")).toBeInTheDocument();
    expect(screen.queryByText("my-app")).toBeNull();
    expect(screen.getByTestId("nav-activity-drawer-btn")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Activity/i })).toBeInTheDocument();
  });

  it("renders coral error counter badge on Activity button when active job has failed commands", () => {
    const onOpenDrawer = vi.fn();
    render(
      <AppNavigation
        activeJob={dummyJob}
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
        onOpenDrawer={onOpenDrawer}
        failedCommandCount={0}
      />
    );

    const btn = screen.getByTestId("nav-activity-drawer-btn");
    fireEvent.click(btn);

    expect(onOpenDrawer).toHaveBeenCalledWith(undefined, undefined);
  });

  it("renders enriched active job pill with stage, feature, and job ID", () => {
    render(
      <AppNavigation
        activeJob={dummyJob}
        onOpenDrawer={vi.fn()}
      />
    );

    const indicator = screen.getByTestId("nav-active-job-indicator");
    expect(indicator).toBeInTheDocument();
    expect(screen.getByText("CODER")).toBeInTheDocument();
    expect(screen.getByText("feature-test")).toBeInTheDocument();
    expect(screen.getByText("job-test-1")).toBeInTheDocument();
  });

  it("triggers onOpenDrawer when clicking anywhere on the active job pill", () => {
    const onOpenDrawer = vi.fn();
    render(
      <AppNavigation
        activeJob={dummyJob}
        onOpenDrawer={onOpenDrawer}
      />
    );

    const indicator = screen.getByTestId("nav-active-job-indicator");
    fireEvent.click(indicator);

    expect(onOpenDrawer).toHaveBeenCalledTimes(1);
  });

  it("renders inline Cancel button when job status is RUNNING and stops propagation on click", () => {
    const onOpenDrawer = vi.fn();
    const onCancelJob = vi.fn();
    render(
      <AppNavigation
        activeJob={dummyJob}
        onOpenDrawer={onOpenDrawer}
        onCancelJob={onCancelJob}
      />
    );

    const cancelBtn = screen.getByTestId("nav-cancel-job-btn");
    expect(cancelBtn).toBeInTheDocument();

    fireEvent.click(cancelBtn);

    expect(onCancelJob).toHaveBeenCalledTimes(1);
    expect(onCancelJob).toHaveBeenCalledWith("job-test-1");
    // Crucial: Drawer should NOT have been opened because propagation stopped
    expect(onOpenDrawer).not.toHaveBeenCalled();
  });

  it("omits inline Cancel button when active job status is not RUNNING", () => {
    const completedJob: Job = {
      ...dummyJob,
      status: "SUCCESS",
    };

    render(
      <AppNavigation
        activeJob={completedJob}
        onOpenDrawer={vi.fn()}
        onCancelJob={vi.fn()}
      />
    );

    expect(screen.queryByTestId("nav-cancel-job-btn")).toBeNull();
  });

  it("falls back to StudioContext.onCancelJob if onCancelJob prop is not provided", () => {
    const onCancelJob = vi.fn();
    render(
      <StudioContext.Provider value={{ onCancelJob } as any}>
        <AppNavigation
          activeJob={dummyJob}
          />
      </StudioContext.Provider>
    );

    const cancelBtn = screen.getByTestId("nav-cancel-job-btn");
    fireEvent.click(cancelBtn);

    expect(onCancelJob).toHaveBeenCalledWith("job-test-1");
  });
});

