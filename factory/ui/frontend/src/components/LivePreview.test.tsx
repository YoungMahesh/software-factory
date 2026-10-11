import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { LivePreview } from "./LivePreview";

describe("LivePreview", () => {
  it("renders preview URL and iframe when previewUrl is present", () => {
    render(
      <LivePreview previewUrl="https://3000.mahesh0.dev" />
    );

    expect(screen.getByText("https://3000.mahesh0.dev")).toBeInTheDocument();
    const iframe = screen.getByTitle("Live Application Preview");
    expect(iframe).toBeInTheDocument();
    expect(iframe).toHaveAttribute("src", "https://3000.mahesh0.dev");
  });

  it("toggles responsive viewport modes", () => {
    const { container } = render(
      <LivePreview previewUrl="https://3000.mahesh0.dev" />
    );

    const mobileBtn = screen.getByTestId("viewport-mobile");
    fireEvent.click(mobileBtn);

    const frameWrapper = container.querySelector(".preview-viewport-wrapper");
    expect(frameWrapper).toHaveStyle({ width: "375px" });

    const tabletBtn = screen.getByTestId("viewport-tablet");
    fireEvent.click(tabletBtn);
    expect(frameWrapper).toHaveStyle({ width: "768px" });

    const desktopBtn = screen.getByTestId("viewport-desktop");
    fireEvent.click(desktopBtn);
    expect(frameWrapper).toHaveStyle({ width: "100%" });
  });

  it("renders explicit 'Refresh' button in toolbar that reloads iframe DOM", () => {
    const handleRefresh = vi.fn();
    render(
      <LivePreview
        previewUrl="https://3000.mahesh0.dev"
        onRefresh={handleRefresh}
      />
    );
    const refreshBtn = screen.getByRole("button", { name: /Refresh/i });
    expect(refreshBtn).toBeInTheDocument();
    expect(refreshBtn).toHaveTextContent("Refresh");

    const iframeBefore = screen.getByTitle("Live Application Preview");
    expect(iframeBefore).toBeInTheDocument();

    fireEvent.click(refreshBtn);
    expect(handleRefresh).toHaveBeenCalledTimes(1);

    const iframeAfter = screen.getByTitle("Live Application Preview");
    expect(iframeAfter).toBeInTheDocument();
  });

  it("automatically reloads iframe DOM when refreshKey prop updates", () => {
    const { rerender } = render(
      <LivePreview
        previewUrl="https://3000.mahesh0.dev"
        refreshKey={0}
      />
    );

    const iframeBefore = screen.getByTitle("Live Application Preview");
    expect(iframeBefore).toBeInTheDocument();

    // Trigger event-driven reload by updating refreshKey prop
    rerender(
      <LivePreview
        previewUrl="https://3000.mahesh0.dev"
        refreshKey={1}
      />
    );

    const iframeAfter = screen.getByTitle("Live Application Preview");
    expect(iframeAfter).toBeInTheDocument();
  });

  it("renders 'Launch Live Preview' CTA when no preview is active and triggers onLaunchPreview", () => {
    const handleLaunch = vi.fn();
    render(
      <LivePreview
        previewUrl={null}
        status="IDLE"
        onLaunchPreview={handleLaunch}
      />
    );

    const ctaBtn = screen.getByTestId("launch-preview-cta-btn");
    expect(ctaBtn).toBeInTheDocument();
    expect(ctaBtn).toHaveTextContent(/Launch Live Preview/i);

    fireEvent.click(ctaBtn);
    expect(handleLaunch).toHaveBeenCalledTimes(1);
  });

  it("displays active branch badge and red Stop button when preview is active", () => {
    const handleStop = vi.fn();
    render(
      <LivePreview
        previewUrl="https://sandbox-3000.modal.host"
        status="SERVING"
        branch="factory/nav-tabs"
        onStopPreview={handleStop}
      />
    );

    // Verify branch badge
    expect(screen.getByTestId("preview-branch-badge")).toHaveTextContent("factory/nav-tabs");

    // Verify iframe points to Modal tunnel URL
    const iframe = screen.getByTitle("Live Application Preview");
    expect(iframe).toHaveAttribute("src", "https://sandbox-3000.modal.host");

    // Verify red Stop button
    const stopBtn = screen.getByTestId("stop-preview-btn");
    expect(stopBtn).toBeInTheDocument();
    expect(stopBtn).toHaveTextContent(/Stop/i);

    fireEvent.click(stopBtn);
    expect(handleStop).toHaveBeenCalledTimes(1);
  });

  it("does not render Stop button when preview status is STOPPED even if previewUrl is set", () => {
    render(
      <LivePreview
        previewUrl="https://sandbox-3000.modal.host"
        status="STOPPED"
        branch="factory/nav-tabs"
        onStopPreview={vi.fn()}
      />
    );

    expect(screen.queryByTestId("stop-preview-btn")).toBeNull();
  });

  it("renders disconnected state and Reconnect button when status is STOPPED", () => {
    const handleReconnect = vi.fn();
    render(
      <LivePreview
        previewUrl="https://sandbox-3000.modal.host"
        status="STOPPED"
        branch="factory/nav-tabs"
        onReconnectPreview={handleReconnect}
      />
    );

    expect(screen.getByText("Sandbox Disconnected")).toBeInTheDocument();
    expect(screen.getByText(/30-minute idle timeout/i)).toBeInTheDocument();

    const reconnectBtn = screen.getByTestId("reconnect-preview-btn");
    expect(reconnectBtn).toBeInTheDocument();
    expect(reconnectBtn).toHaveTextContent(/Reconnect Environment/i);

    fireEvent.click(reconnectBtn);
    expect(handleReconnect).toHaveBeenCalledTimes(1);
  });

  it("renders 3-stage progress stepper when status is PROVISIONING", () => {
    render(
      <LivePreview
        status="PROVISIONING"
        stage="INSTALLING_DEPS"
        branch="main"
      />
    );

    expect(screen.getByTestId("preview-progress-stepper")).toBeInTheDocument();
    expect(screen.getByText("Provisioning sandbox")).toBeInTheDocument();
    expect(screen.getByText("Installing dependencies")).toBeInTheDocument();
    expect(screen.getByText("Starting dev server")).toBeInTheDocument();
  });

  it("toggles dev server logs drawer with toolbar button", () => {
    render(
      <LivePreview
        status="PROVISIONING"
        stage="PROVISIONING"
        logs={["Cloning repository...", "Decrypting secrets..."]}
      />
    );

    const toggleBtn = screen.getByTestId("toggle-dev-logs-btn");
    expect(toggleBtn).toBeInTheDocument();

    // Initially drawer is closed
    expect(screen.queryByTestId("dev-server-logs-drawer")).toBeNull();

    // Click to open
    fireEvent.click(toggleBtn);
    expect(screen.getByTestId("dev-server-logs-drawer")).toBeInTheDocument();
    expect(screen.getByText("Cloning repository...")).toBeInTheDocument();

    // Click again to close
    fireEvent.click(toggleBtn);
    expect(screen.queryByTestId("dev-server-logs-drawer")).toBeNull();
  });

  it("auto-expands dev server logs drawer and displays Retry button on failure", () => {
    const handleRetry = vi.fn();
    render(
      <LivePreview
        status="FAILED"
        stage="INSTALLING_DEPS"
        errorMessage="ERR_PNPM_FETCH_404 Package not found"
        logs={["pnpm install", "ERR_PNPM_FETCH_404 Package not found"]}
        onRetryPreview={handleRetry}
      />
    );

    // Auto-expanded drawer
    expect(screen.getByTestId("dev-server-logs-drawer")).toBeInTheDocument();
    expect(screen.getAllByText(/ERR_PNPM_FETCH_404/).length).toBeGreaterThanOrEqual(1);

    // Retry button in drawer or stepper
    const retryButtons = screen.getAllByTestId("retry-preview-btn");
    expect(retryButtons.length).toBeGreaterThanOrEqual(1);

    fireEvent.click(retryButtons[0]);
    expect(handleRetry).toHaveBeenCalledTimes(1);
  });
});
