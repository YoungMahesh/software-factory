import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "../../test/test-utils";
import { InStudioCodeViewer } from "./InStudioCodeViewer";
import * as api from "../../api";

vi.mock("../../api", async () => {
  const actual = await vi.importActual("../../api");
  return {
    ...actual,
    fetchRepoTree: vi.fn(),
    fetchRepoFile: vi.fn(),
  };
});

describe("InStudioCodeViewer", () => {
  const mockTreeResponse: api.RepoTreeResponse = {
    repo: "cool-app",
    branch: "main",
    source: "github",
    tree: [
      { path: "package.json", type: "blob", size: 450 },
      { path: "src", type: "tree" },
      { path: "src/App.tsx", type: "blob", size: 1200 },
      { path: "src/utils.ts", type: "blob", size: 300 },
      { path: "large_data.json", type: "blob", size: 600000 },
      { path: "assets/logo.png", type: "blob", size: 4096 },
    ],
  };

  const mockAppTsxResponse: api.RepoFileResponse = {
    repo: "cool-app",
    branch: "main",
    path: "src/App.tsx",
    size: 1200,
    is_binary: false,
    is_truncated: false,
    content: "import React from 'react';\n\nexport const App = () => {\n  return <div>Hello World</div>;\n};\n",
    language: "typescript",
    source: "github",
  };

  const mockLargeFileResponse: api.RepoFileResponse = {
    repo: "cool-app",
    branch: "main",
    path: "large_data.json",
    size: 600000,
    is_binary: false,
    is_truncated: true,
    content: null,
    message: "File exceeds 500KB inspection ceiling (585.9 KB).",
    source: "github",
  };

  const mockBinaryFileResponse: api.RepoFileResponse = {
    repo: "cool-app",
    branch: "main",
    path: "assets/logo.png",
    size: 4096,
    is_binary: true,
    is_truncated: false,
    content: null,
    message: "Binary file cannot be displayed.",
    source: "github",
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.fetchRepoTree).mockResolvedValue(mockTreeResponse);
    vi.mocked(api.fetchRepoFile).mockImplementation(async (_repo, path) => {
      if (path === "src/App.tsx") return mockAppTsxResponse;
      if (path === "large_data.json") return mockLargeFileResponse;
      if (path === "assets/logo.png") return mockBinaryFileResponse;
      return {
        repo: "cool-app",
        branch: "main",
        path,
        size: 100,
        is_binary: false,
        is_truncated: false,
        content: `// Content of ${path}`,
        source: "github",
      };
    });
  });

  it("renders tree items and allows expanding folders", async () => {
    const { user } = renderWithProviders(
      <InStudioCodeViewer repo="cool-app" branch="main" />
    );

    await waitFor(() => {
      expect(screen.getByText("package.json")).toBeInTheDocument();
      expect(screen.getByText("src")).toBeInTheDocument();
    });

    // In initial tree view, src/App.tsx should be visible inside folder or upon expanding
    expect(screen.getByText("App.tsx")).toBeInTheDocument();

    // Search filter filters items
    const searchInput = screen.getByPlaceholderText(/filter files/i);
    await user.type(searchInput, "utils");

    expect(screen.getByText("utils.ts")).toBeInTheDocument();
    expect(screen.queryByText("package.json")).not.toBeInTheDocument();
  });

  it("selects a file and displays source code with line numbers", async () => {
    const { user } = renderWithProviders(
      <InStudioCodeViewer repo="cool-app" branch="main" />
    );

    await waitFor(() => {
      expect(screen.getByText("App.tsx")).toBeInTheDocument();
    });

    // Click App.tsx
    await user.click(screen.getByText("App.tsx"));

    await waitFor(() => {
      expect(api.fetchRepoFile).toHaveBeenCalledWith("cool-app", "src/App.tsx", "main");
      expect(screen.getByText("Hello")).toBeInTheDocument();
    });

    // Line numbers should be rendered
    expect(screen.getByTestId("line-number-1")).toBeInTheDocument();
    expect(screen.getByTestId("line-number-2")).toBeInTheDocument();

    // File header displays path and language
    expect(screen.getByText("src/App.tsx")).toBeInTheDocument();
    expect(screen.getByText("typescript")).toBeInTheDocument();
  });

  it("renders safe placeholder for files exceeding 500KB cap", async () => {
    const { user } = renderWithProviders(
      <InStudioCodeViewer repo="cool-app" branch="main" />
    );

    await waitFor(() => {
      expect(screen.getByText("large_data.json")).toBeInTheDocument();
    });

    await user.click(screen.getByText("large_data.json"));

    await waitFor(() => {
      expect(screen.getByText(/File Exceeds Size Ceiling/i)).toBeInTheDocument();
      expect(screen.getByText(/File exceeds 500KB inspection ceiling/i)).toBeInTheDocument();
    });
  });

  it("renders safe placeholder for binary files", async () => {
    const { user } = renderWithProviders(
      <InStudioCodeViewer repo="cool-app" branch="main" />
    );

    await waitFor(() => {
      expect(screen.getByText("logo.png")).toBeInTheDocument();
    });

    await user.click(screen.getByText("logo.png"));

    await waitFor(() => {
      expect(screen.getByText(/Binary File Detected/i)).toBeInTheDocument();
      expect(screen.getByText(/Binary file cannot be displayed/i)).toBeInTheDocument();
    });
  });

  it("copies code content when copy button is clicked", async () => {
    const { user } = renderWithProviders(
      <InStudioCodeViewer repo="cool-app" branch="main" initialPath="src/App.tsx" />
    );

    const writeSpy = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);

    await waitFor(() => {
      expect(screen.getByText("Hello")).toBeInTheDocument();
    });

    const copyBtn = screen.getByTestId("copy-code-button");
    await user.click(copyBtn);

    await waitFor(() => {
      expect(writeSpy).toHaveBeenCalledWith(mockAppTsxResponse.content);
      expect(screen.getByText(/Copied/i)).toBeInTheDocument();
    });
  });
});
