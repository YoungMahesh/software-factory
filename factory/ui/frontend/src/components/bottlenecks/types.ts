import { AgentEvent } from "../../types";

export type InfrastructureCategory =
  | "Package Install"
  | "Test Suite"
  | "Build / Compile"
  | "Git / VCS"
  | "LLM Thinking"
  | "Command";

export type StageFilter = "All" | "Planner" | "Coder" | "Verifier" | "Reviewer";

export type CategoryFilter = "All" | "Commands" | "Thinking";

export interface BottleneckItem {
  id: string;
  type: "command" | "thinking";
  title: string;
  durationMs: number;
  stage?: string;
  exitCode?: number;
  isError?: boolean;
  output?: string;
  stderr?: string;
  cwd?: string;
  category: InfrastructureCategory;
}

export interface BottlenecksViewerProps {
  events?: AgentEvent[];
}
