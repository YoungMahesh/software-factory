import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "../../test/test-utils";
import { PreMergeDiffViewer } from "./PreMergeDiffViewer";
import * as api from "../../api";

vi.mock("../../api", async () => {
  const actual = await vi.importActual("../../api");
  return {
    ...actual,
    fetchRepoDiff: vi.fn(),
  };
});

describe("PreMergeDiffViewer", () => {
  const mockWorkingTreeDiff: api.RepoDiffResponse = {
    repo: "factory-app",
    branch: "factory/feature-checkout",
    base: "main",
    scope: "working_tree",
    source: "sandbox",
    summary: {
      total_files: 2,
      additions: 15,
      deletions: 4,
    },
    files: [
      {
        path: "src/components/Checkout.tsx",
        status: "modified",
        additions: 10,
        deletions: 4,
        patch:
          "@@ -10,4 +10,10 @@ export function Checkout() {\n" +
          "   const cart = useCart();\n" +
          "-  const total = 0;\n" +
          "+  const [total, setTotal] = useState(0);\n" +
          "+  const isValid = true;\n" +
          "   return <div />;\n" +
          " }\n",
      },
      {
        path: "src/utils/tax.ts",
        status: "added",
        additions: 5,
        deletions: 0,
        patch:
          "@@ -0,0 +1,5 @@\n" +
          "+export function calcTax(amount: number) {\n" +
          "+  return amount * 0.1;\n" +
          "+}\n",
      },
    ],
    clean: false,
  };

  const mockBranchDiff: api.RepoDiffResponse = {
    repo: "factory-app",
    branch: "factory/feature-checkout",
    base: "main",
    scope: "branch",
    source: "github",
    summary: {
      total_files: 1,
      additions: 25,
      deletions: 2,
    },
    files: [
      {
        path: "src/api/payment.ts",
        status: "modified",
        additions: 25,
        deletions: 2,
        patch:
          "@@ -1,3 +1,5 @@\n" +
          "-export const api = null;\n" +
          "+export const api = initStripe();\n" +
          "+export const pay = () => {};\n",
      },
    ],
    clean: false,
  };

  const mockCleanDiff: api.RepoDiffResponse = {
    repo: "factory-app",
    branch: "main",
    base: "main",
    scope: "working_tree",
    source: "sandbox",
    summary: {
      total_files: 0,
      additions: 0,
      deletions: 0,
    },
    files: [],
    clean: true,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the summary header and expandable accordion cards for modified files", async () => {
    vi.mocked(api.fetchRepoDiff).mockResolvedValueOnce(mockWorkingTreeDiff);

    renderWithProviders(
      <PreMergeDiffViewer repo="factory-app" branch="factory/feature-checkout" />
    );

    expect(screen.getByTestId("pre-merge-diff-viewer")).toBeInTheDocument();

    await waitFor(() => {
      // Summary header
      expect(screen.getByTestId("diff-summary-files")).toHaveTextContent("2 modified files");
      expect(screen.getByTestId("diff-summary-additions")).toHaveTextContent("+15");
      expect(screen.getByTestId("diff-summary-deletions")).toHaveTextContent("-4");

      // File cards
      expect(screen.getByText("src/components/Checkout.tsx")).toBeInTheDocument();
      expect(screen.getByText("src/utils/tax.ts")).toBeInTheDocument();
    });

    // Verify badges per file card
    expect(screen.getByTestId("file-additions-src/components/Checkout.tsx")).toHaveTextContent("+10");
    expect(screen.getByTestId("file-deletions-src/components/Checkout.tsx")).toHaveTextContent("-4");
  });

  it("toggles card collapse and expansion when clicking file header", async () => {
    vi.mocked(api.fetchRepoDiff).mockResolvedValueOnce(mockWorkingTreeDiff);

    const { user } = renderWithProviders(
      <PreMergeDiffViewer repo="factory-app" branch="factory/feature-checkout" />
    );

    await waitFor(() => {
      expect(screen.getByText("src/components/Checkout.tsx")).toBeInTheDocument();
    });

    // Content is visible initially (expanded by default)
    expect(screen.getByText(/setTotal/)).toBeInTheDocument();

    // Click to collapse
    const cardToggle = screen.getByTestId("diff-card-toggle-src/components/Checkout.tsx");
    await user.click(cardToggle);

    // Patch should not be visible when collapsed
    expect(screen.queryByText(/setTotal/)).not.toBeInTheDocument();

    // Click to expand again
    await user.click(cardToggle);
    expect(screen.getByText(/setTotal/)).toBeInTheDocument();
  });

  it("allows switching layout between Unified hunk view and Split side-by-side view", async () => {
    vi.mocked(api.fetchRepoDiff).mockResolvedValueOnce(mockWorkingTreeDiff);

    const { user } = renderWithProviders(
      <PreMergeDiffViewer repo="factory-app" branch="factory/feature-checkout" />
    );

    await waitFor(() => {
      expect(screen.getByTestId("unified-diff-src/components/Checkout.tsx")).toBeInTheDocument();
    });

    // Initially in Unified view
    expect(screen.getByTestId("layout-toggle-unified")).toHaveClass("bg-primary");

    // Switch to Split side-by-side view
    await user.click(screen.getByTestId("layout-toggle-split"));

    await waitFor(() => {
      expect(screen.getByTestId("layout-toggle-split")).toHaveClass("bg-primary");
      expect(screen.getByTestId("split-diff-src/components/Checkout.tsx")).toBeInTheDocument();
    });

    // Verify side-by-side alignment: split table contains left and right cells
    const splitContainer = screen.getByTestId("split-diff-src/components/Checkout.tsx");
    expect(splitContainer).toBeInTheDocument();
    expect(splitContainer.querySelector(".diff-split-left")).toBeInTheDocument();
    expect(splitContainer.querySelector(".diff-split-right")).toBeInTheDocument();
  });

  it("toggles between Working Tree Changes and Branch Changes scopes", async () => {
    vi.mocked(api.fetchRepoDiff)
      .mockResolvedValueOnce(mockWorkingTreeDiff)
      .mockResolvedValueOnce(mockBranchDiff);

    const { user } = renderWithProviders(
      <PreMergeDiffViewer repo="factory-app" branch="factory/feature-checkout" />
    );

    await waitFor(() => {
      expect(screen.getByTestId("diff-scope-working_tree")).toHaveClass("bg-primary");
      expect(screen.getByText("src/components/Checkout.tsx")).toBeInTheDocument();
    });

    // Switch to Branch Changes
    await user.click(screen.getByTestId("diff-scope-branch"));

    await waitFor(() => {
      expect(api.fetchRepoDiff).toHaveBeenCalledWith(
        "factory-app",
        "branch",
        "factory/feature-checkout",
        "main"
      );
      expect(screen.getByTestId("diff-scope-branch")).toHaveClass("bg-primary");
      expect(screen.getByText("src/api/payment.ts")).toBeInTheDocument();
      expect(screen.getByTestId("diff-summary-files")).toHaveTextContent("1 modified file");
      expect(screen.getByTestId("diff-summary-additions")).toHaveTextContent("+25");
    });
  });

  it("renders clean empty state when no changes exist in the active scope", async () => {
    vi.mocked(api.fetchRepoDiff).mockResolvedValueOnce(mockCleanDiff);

    renderWithProviders(
      <PreMergeDiffViewer repo="factory-app" branch="main" />
    );

    await waitFor(() => {
      expect(screen.getByTestId("diff-empty-state")).toBeInTheDocument();
      expect(screen.getByText("No Working Tree Changes")).toBeInTheDocument();
      expect(screen.getByText(/Container filesystem is clean/)).toBeInTheDocument();
    });
  });
});
