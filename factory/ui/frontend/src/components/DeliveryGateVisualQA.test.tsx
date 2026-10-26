import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DeliveryGateCard } from "./DeliveryGateCard";
import * as api from "../api";
import { PullRequest, DeliveryGateData, VisualQaTelemetry } from "../types";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    fetchPullRequests: vi.fn(),
    mergePullRequest: vi.fn(),
    markPullRequestReadyForReview: vi.fn(),
    fetchVisualQa: vi.fn(),
  };
});

describe("DeliveryGateCard Visual QA Telemetry & Modal", () => {
  let queryClient: QueryClient;

  const mockPR: PullRequest = {
    id: 201,
    number: 42,
    title: "Feature: Landing Page Redesign",
    body: "- Fixes #10",
    state: "open",
    status: "ready_for_review",
    draft: false,
    merged: false,
    mergeable: true,
    mergeable_state: "clean",
    head_branch: "factory/landing-redesign",
    base_branch: "main",
    html_url: "https://github.com/software-factory-09-test/app/pull/42",
  };

  const passingVisualQa: VisualQaTelemetry = {
    passed: true,
    status: "passed",
    cleanCanvas: true,
    errors: [],
    desktop_url: "/api/repos/app/visual-qa/screenshot?viewport=desktop",
    mobile_url: "/api/repos/app/visual-qa/screenshot?viewport=mobile",
    captured_at: 1729900500.0,
  };

  const failingVisualQa: VisualQaTelemetry = {
    passed: false,
    status: "failed",
    cleanCanvas: false,
    errors: [
      "Uncaught TypeError: Cannot read property 'map' of undefined",
      "Clean Canvas Invariant failed: #root has 0x0 dimensions",
    ],
    desktop_url: "/api/repos/app/visual-qa/screenshot?viewport=desktop",
    mobile_url: null,
    captured_at: 1729900510.0,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    vi.mocked(api.fetchPullRequests).mockResolvedValue({
      repo: "app",
      pulls: [mockPR],
    });
    vi.mocked(api.fetchVisualQa).mockResolvedValue(passingVisualQa);
  });

  const renderCard = (props: Partial<React.ComponentProps<typeof DeliveryGateCard>> = {}) => {
    const data: DeliveryGateData = {
      phase: "finalized",
      pull_number: 42,
      pull_request: mockPR,
      test_verdict: "deterministic_tests_passed",
      ...props.data,
    };
    return render(
      <QueryClientProvider client={queryClient}>
        <DeliveryGateCard repo="app" data={data} {...props} />
      </QueryClientProvider>
    );
  };

  it("renders 'Visual QA Verified' status badge alongside deterministic test verdict when passed", () => {
    renderCard({
      data: {
        pull_number: 42,
        pull_request: mockPR,
        visual_qa: passingVisualQa,
      },
    });

    expect(screen.getByTestId("delivery-gate-verifier-verdict")).toHaveTextContent("Deterministic Tests Passing");
    const vqaBadge = screen.getByTestId("visual-qa-status-badge");
    expect(vqaBadge).toBeInTheDocument();
    expect(vqaBadge).toHaveTextContent("Visual QA Verified");
  });

  it("renders 'Visual QA Failed' badge and warning telemetry when visual verification fails", () => {
    vi.mocked(api.fetchVisualQa).mockResolvedValue(failingVisualQa);

    renderCard({
      data: {
        pull_number: 42,
        pull_request: mockPR,
        visual_qa: failingVisualQa,
      },
    });

    const vqaBadge = screen.getByTestId("visual-qa-status-badge");
    expect(vqaBadge).toHaveTextContent("Visual QA Failed");

    // Warning telemetry section
    const errorTelemetry = screen.getByTestId("visual-qa-error-telemetry");
    expect(errorTelemetry).toBeInTheDocument();
    expect(errorTelemetry).toHaveTextContent("Visual Verification Failed — Merge Blocked");
    expect(errorTelemetry).toHaveTextContent("Cannot read property 'map' of undefined");
    expect(errorTelemetry).toHaveTextContent("Clean Canvas Invariant failed");
  });

  it("disables In-Studio Merge Control when visual verification fails", () => {
    vi.mocked(api.fetchVisualQa).mockResolvedValue(failingVisualQa);

    renderCard({
      data: {
        pull_number: 42,
        pull_request: mockPR,
        visual_qa: failingVisualQa,
      },
    });

    const mergeBtn = screen.getByTestId("btn-delivery-gate-merge");
    expect(mergeBtn).toBeDisabled();
    expect(mergeBtn).toHaveAttribute("title", expect.stringContaining("Visual QA verification failed"));
    expect(screen.getByText("Blocked by Visual QA failures")).toBeInTheDocument();
  });

  it("renders screenshot thumbnail with desktop and mobile capture indicators", () => {
    renderCard({
      data: {
        pull_number: 42,
        pull_request: mockPR,
        visual_qa: passingVisualQa,
      },
    });

    const thumbnail = screen.getByTestId("delivery-gate-screenshot-thumbnail");
    expect(thumbnail).toBeInTheDocument();

    const desktopIndicator = screen.getByTestId("vqa-desktop-status");
    expect(desktopIndicator).toHaveTextContent("Desktop ✓");

    const mobileIndicator = screen.getByTestId("vqa-mobile-status");
    expect(mobileIndicator).toHaveTextContent("Mobile ✓");
  });

  it("renders pending indicators when viewports are not captured", () => {
    const pendingVisualQa: VisualQaTelemetry = {
      passed: false,
      status: "pending",
      errors: [],
      desktop_url: null,
      mobile_url: null,
    };
    vi.mocked(api.fetchVisualQa).mockResolvedValue(pendingVisualQa);

    renderCard({
      data: {
        pull_number: 42,
        pull_request: mockPR,
        visual_qa: pendingVisualQa,
      },
    });

    const desktopIndicator = screen.getByTestId("vqa-desktop-status");
    expect(desktopIndicator).toHaveTextContent("Desktop —");

    const mobileIndicator = screen.getByTestId("vqa-mobile-status");
    expect(mobileIndicator).toHaveTextContent("Mobile —");
  });

  it("opens high-resolution modal on thumbnail click and allows viewport switching and closing", async () => {
    const user = userEvent.setup();
    renderCard({
      data: {
        pull_number: 42,
        pull_request: mockPR,
        visual_qa: passingVisualQa,
      },
    });

    // Modal is initially not in DOM
    expect(screen.queryByTestId("visual-qa-modal")).not.toBeInTheDocument();

    // Click thumbnail
    const thumbnail = screen.getByTestId("delivery-gate-screenshot-thumbnail");
    await user.click(thumbnail);

    // Modal is now open
    const modal = screen.getByTestId("visual-qa-modal");
    expect(modal).toBeInTheDocument();

    // Displays desktop screenshot by default
    const img = screen.getByTestId("visual-qa-modal-image");
    expect(img).toHaveAttribute("src", passingVisualQa.desktop_url);

    // Switch to mobile viewport
    const mobileToggle = screen.getByTestId("vqa-modal-toggle-mobile");
    await user.click(mobileToggle);

    // Image src updates to mobile URL
    expect(screen.getByTestId("visual-qa-modal-image")).toHaveAttribute("src", passingVisualQa.mobile_url);

    // Close modal via close button
    const closeBtn = screen.getByTestId("visual-qa-modal-close-btn");
    await user.click(closeBtn);

    // Modal is closed
    expect(screen.queryByTestId("visual-qa-modal")).not.toBeInTheDocument();
  });
});
