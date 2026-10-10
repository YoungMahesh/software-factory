import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { DiffViewer } from "./DiffViewer";

describe("DiffViewer", () => {
  const patch =
    "--- a/src/app.tsx\n+++ b/src/app.tsx\n@@ -1,3 +1,4 @@\n const a = 1;\n+const a = 2;\n-const b = 3;\n";

  it("parses and renders additions and deletions", () => {
    render(
      <DiffViewer
        path="src/app.tsx"
        diff={patch}
        stage="CODER"
      />
    );

    expect(screen.getByText("src/app.tsx")).toBeInTheDocument();
    expect(screen.getByText("+1")).toBeInTheDocument();
    expect(screen.getByText("-1")).toBeInTheDocument();

    expect(screen.getByText("+const a = 2;")).toBeInTheDocument();
    expect(screen.getByText("-const b = 3;")).toBeInTheDocument();
  });

  it("can be collapsed and expanded", () => {
    render(
      <DiffViewer
        path="src/app.tsx"
        diff={patch}
        defaultExpanded={false}
      />
    );

    expect(screen.queryByText("+const a = 2;")).not.toBeInTheDocument();

    const toggleBtn = screen.getByRole("button");
    fireEvent.click(toggleBtn);

    expect(screen.getByText("+const a = 2;")).toBeInTheDocument();
  });
});
