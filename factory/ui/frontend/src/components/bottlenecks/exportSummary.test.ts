import { describe, it, expect } from "vitest";
import { formatBottlenecksMarkdown, formatRepoBottlenecksMarkdown } from "./exportSummary";
import { BottleneckItem } from "./types";
import { RepoBottleneck } from "../../types";

describe("exportSummary", () => {
  describe("formatBottlenecksMarkdown", () => {
    it("formats an empty list with standard markdown table headers", () => {
      const result = formatBottlenecksMarkdown([]);
      expect(result).toBe(
        "| Rank | Category | Stage | Operation | Duration | Status |\n| ---: | :--- | :--- | :--- | ---: | :--- |"
      );
    });

    it("formats bottleneck items into a clean GitHub-flavored markdown table", () => {
      const items: BottleneckItem[] = [
        {
          id: "1",
          type: "command",
          title: "pnpm build",
          durationMs: 4200,
          stage: "CODER",
          exitCode: 0,
          category: "Build / Compile",
        },
        {
          id: "2",
          type: "thinking",
          title: "LLM Thinking (PLANNER)",
          durationMs: 2500,
          stage: "PLANNER",
          category: "LLM Thinking",
        },
        {
          id: "3",
          type: "command",
          title: "pytest tests/",
          durationMs: 1800,
          stage: "VERIFIER",
          exitCode: 1,
          isError: true,
          category: "Test Suite",
        },
        {
          id: "4",
          type: "command",
          title: "git status",
          durationMs: 45,
          stage: "CODER",
          category: "Git / VCS",
        },
      ];

      const md = formatBottlenecksMarkdown(items);
      const lines = md.split("\n");

      expect(lines[0]).toBe("| Rank | Category | Stage | Operation | Duration | Status |");
      expect(lines[1]).toBe("| ---: | :--- | :--- | :--- | ---: | :--- |");
      expect(lines[2]).toBe("| 1 | Build / Compile | CODER | `pnpm build` | 4.20s (4200ms) | Exit 0 |");
      expect(lines[3]).toBe("| 2 | LLM Thinking | PLANNER | LLM Thinking (PLANNER) | 2.50s (2500ms) | Success |");
      expect(lines[4]).toBe("| 3 | Test Suite | VERIFIER | `pytest tests/` | 1.80s (1800ms) | Exit 1 |");
      expect(lines[5]).toBe("| 4 | Git / VCS | CODER | `git status` | 0.04s (45ms) | Success |");
    });

    it("sanitizes pipes and multiline commands to maintain table integrity", () => {
      const items: BottleneckItem[] = [
        {
          id: "1",
          type: "command",
          title: "cat file.txt | grep 'pattern'\n--sort",
          durationMs: 300,
          stage: "CODER",
          exitCode: 0,
          category: "Command",
        },
      ];

      const md = formatBottlenecksMarkdown(items);
      const lines = md.split("\n");
      expect(lines[2]).toBe("| 1 | Command | CODER | `cat file.txt \\| grep 'pattern' --sort` | 0.30s (300ms) | Exit 0 |");
    });

    it("handles commands with isError=true when exitCode is omitted", () => {
      const items: BottleneckItem[] = [
        {
          id: "1",
          type: "command",
          title: "unknown-cmd",
          durationMs: 120,
          stage: "CODER",
          isError: true,
          category: "Command",
        },
      ];

      const md = formatBottlenecksMarkdown(items);
      expect(md).toContain("| 1 | Command | CODER | `unknown-cmd` | 0.12s (120ms) | Error |");
    });
  });

  describe("formatRepoBottlenecksMarkdown", () => {
    it("formats empty repo bottlenecks list", () => {
      const result = formatRepoBottlenecksMarkdown("my-repo", []);
      expect(result).toBe(
        "| Rank | Operation | Category | Stage | Total Duration | Invocations | Avg Duration | Max Duration |\n| ---: | :--- | :--- | :--- | ---: | ---: | ---: | ---: |"
      );
    });

    it("formats repo bottlenecks into markdown table", () => {
      const bottlenecks: RepoBottleneck[] = [
        {
          command: "pnpm install",
          category: "Package Install",
          stage: "CODER",
          count: 5,
          invocation_count: 5,
          total_duration_ms: 15000,
          avg_duration_ms: 3000,
          max_duration_ms: 4500,
        },
        {
          command: "LLM Thinking (PLANNER)",
          category: "LLM Thinking",
          stage: "PLANNER",
          count: 3,
          invocation_count: 3,
          total_duration_ms: 9000,
          avg_duration_ms: 3000,
          max_duration_ms: 4000,
        },
      ];

      const md = formatRepoBottlenecksMarkdown("test-org/test-repo", bottlenecks);
      const lines = md.split("\n");

      expect(lines[0]).toBe("| Rank | Operation | Category | Stage | Total Duration | Invocations | Avg Duration | Max Duration |");
      expect(lines[1]).toBe("| ---: | :--- | :--- | :--- | ---: | ---: | ---: | ---: |");
      expect(lines[2]).toBe("| 1 | `pnpm install` | Package Install | CODER | 15.00s | 5 | 3.00s | 4.50s |");
      expect(lines[3]).toBe("| 2 | LLM Thinking (PLANNER) | LLM Thinking | PLANNER | 9.00s | 3 | 3.00s | 4.00s |");
    });
  });
});
