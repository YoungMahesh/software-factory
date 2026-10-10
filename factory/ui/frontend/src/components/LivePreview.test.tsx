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

  it("renders reload button", () => {
    render(<LivePreview previewUrl="https://3000.mahesh0.dev" />);
    const reloadBtn = screen.getByTestId("reload-preview-btn");
    expect(reloadBtn).toBeInTheDocument();
    fireEvent.click(reloadBtn);
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
});
