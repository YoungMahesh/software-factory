import { InfrastructureCategory } from "./types";

interface ClassifyParams {
  type: "command" | "thinking";
  command?: string;
  stage?: string;
}

/**
 * Classifies an operation into an infrastructure category based on command heuristics
 * and pipeline stage metadata.
 */
export function classifyBottleneck({
  type,
  command = "",
  stage = "",
}: ClassifyParams): InfrastructureCategory {
  if (type === "thinking") {
    return "LLM Thinking";
  }

  const cleanCmd = (command || "").trim();
  // Strip leading variable assignments or common prefixes like `export FOO=bar &&` or `sudo`
  const normalized = cleanCmd
    .replace(/^(?:export\s+[A-Za-z0-9_]+=\S*\s*&&?\s*)+/i, "")
    .replace(/^sudo\s+/i, "")
    .trim();

  // 1. Git / VCS: git commands
  if (/^git(?:\.exe)?(?:\s+.*)?$/i.test(normalized)) {
    return "Git / VCS";
  }

  // 2. Package Install: dependency managers
  if (
    /^(?:pnpm|npm|yarn|bun)\s+(?:install|add|i)\b/i.test(normalized) ||
    /^(?:pip|pip3|uv\s+pip)\s+install\b/i.test(normalized) ||
    /^poetry\s+(?:install|add)\b/i.test(normalized) ||
    /^cargo\s+(?:add|install)\b/i.test(normalized)
  ) {
    return "Package Install";
  }

  // 3. Build / Compile: bundlers, compilers, build scripts
  if (
    /^(?:pnpm|npm|yarn|bun)\s+(?:run\s+)?build\b/i.test(normalized) ||
    /^(?:npx\s+|pnpm\s+dlx\s+)?(?:tsc|vite\s+build|webpack|esbuild|rollup|next\s+build|turbo\s+build)\b/i.test(
      normalized
    ) ||
    /^(?:cargo\s+build|make\b|gcc\b|g\+\+\b)/i.test(normalized)
  ) {
    return "Build / Compile";
  }

  // 4. Test Suite: test runners, framework runners, or fallback for VERIFIER stage
  if (
    /^(?:pnpm|npm|yarn|bun)\s+(?:run\s+)?test\b/i.test(normalized) ||
    /^(?:npx\s+|pnpm\s+dlx\s+)?(?:vitest|jest|pytest|playwright|cypress)\b/i.test(normalized) ||
    /^(?:python3?|py)\s+-m\s+pytest\b/i.test(normalized) ||
    /^(?:go|cargo)\s+test\b/i.test(normalized) ||
    stage?.toUpperCase() === "VERIFIER"
  ) {
    return "Test Suite";
  }

  return "Command";
}

/**
 * Returns Tailwind color styling classes for each infrastructure category badge.
 */
export function getCategoryBadgeStyle(category: InfrastructureCategory): string {
  switch (category) {
    case "Package Install":
      return "bg-amber-500/10 text-amber-700 border-amber-300 dark:bg-amber-950/30 dark:text-amber-400 dark:border-amber-800";
    case "Test Suite":
      return "bg-emerald-500/10 text-emerald-700 border-emerald-300 dark:bg-emerald-950/30 dark:text-emerald-400 dark:border-emerald-800";
    case "Build / Compile":
      return "bg-blue-500/10 text-blue-700 border-blue-300 dark:bg-blue-950/30 dark:text-blue-400 dark:border-blue-800";
    case "Git / VCS":
      return "bg-slate-500/10 text-slate-700 border-slate-300 dark:bg-slate-800/40 dark:text-slate-300 dark:border-slate-700";
    case "LLM Thinking":
      return "bg-purple-500/10 text-purple-700 border-purple-300 dark:bg-purple-950/30 dark:text-purple-400 dark:border-purple-800";
    case "Command":
    default:
      return "bg-soft-stone text-ink border-hairline";
  }
}
