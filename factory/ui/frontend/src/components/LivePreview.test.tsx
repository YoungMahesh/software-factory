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
});
