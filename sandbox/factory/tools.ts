import { execFile } from "node:child_process";
import { promisify } from "node:util";
import {
  createReadTool,
  createGrepTool,
  createFindTool,
  createLsTool,
  createWriteTool,
  createEditTool,
  createBashTool,
} from "@earendil-works/pi-coding-agent";
import { Type } from "@earendil-works/pi-ai";

const pExecFile = promisify(execFile);

export const AGENT_ROLES = ["planner", "coder", "reviewer"] as const;
export type AgentRole = (typeof AGENT_ROLES)[number];

export const ROLE_ALLOWED_TOOLS: Record<AgentRole, readonly string[]> = {
  planner: ["read", "grep", "find", "ls"],
  coder: ["read", "write", "edit", "bash", "diff"],
  reviewer: ["read", "grep", "find", "ls", "diff"],
};

export const FORBIDDEN_MUTATING_TOOLS = ["write", "edit", "bash"] as const;

export class LeastPrivilegeViolationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "LeastPrivilegeViolationError";
  }
}

/**
 * Validates that the provided tool names adhere strictly to the least-privilege boundary
 * for the given agent role. Throws LeastPrivilegeViolationError if any forbidden tools exist.
 */
export function assertRoleToolPrivileges(role: AgentRole, toolNames: string[]): void {
  const allowed = ROLE_ALLOWED_TOOLS[role];
  if (!allowed) {
    throw new LeastPrivilegeViolationError(`Unknown agent role: "${role}"`);
  }

  // Strictly enforce that read-only roles (planner, reviewer) never have write, edit, or bash tools
  if (role === "planner" || role === "reviewer") {
    for (const tool of toolNames) {
      if ((FORBIDDEN_MUTATING_TOOLS as readonly string[]).includes(tool)) {
        throw new LeastPrivilegeViolationError(
          `Least-privilege violation: Role "${role}" must be strictly read-only, but received forbidden mutating tool "${tool}".`
        );
      }
    }
  }

  // Enforce that all tools are among the allowed tools for this role
  for (const tool of toolNames) {
    if (!allowed.includes(tool)) {
      throw new LeastPrivilegeViolationError(
        `Tool "${tool}" is not permitted for role "${role}". Allowed tools: ${allowed.join(", ")}`
      );
    }
  }
}

/**
 * Creates a read-only git diff inspection tool suitable for both Coder and Reviewer stages.
 */
export function createGitDiffTool(workspaceDir: string) {
  return {
    name: "diff",
    description: "Inspect git diff of working tree changes, staged changes, or against a commit/branch in the target repository.",
    parameters: Type.Object({
      cached: Type.Optional(Type.Boolean({ description: "View staged changes only (--cached / --staged)" })),
      commit: Type.Optional(Type.String({ description: "Specific commit or revision to diff against (e.g. HEAD, origin/main)" })),
      path: Type.Optional(Type.String({ description: "Specific file or directory path to diff" })),
    }),
    execute: async (
      _toolCallId: string,
      params: { cached?: boolean; commit?: string; path?: string },
      _signal?: AbortSignal
    ) => {
      const args = ["diff"];
      if (params.cached) {
        args.push("--staged");
      }
      if (params.commit) {
        if (params.commit.startsWith("-")) {
          return {
            content: [{ type: "text" as const, text: "Error: Commit revision cannot start with a dash." }],
          };
        }
        args.push(params.commit);
      }
      if (params.path) {
        args.push("--", params.path);
      }

      try {
        const { stdout, stderr } = await pExecFile("git", args, {
          cwd: workspaceDir,
          maxBuffer: 10 * 1024 * 1024,
        });

        const output = stdout.trim();
        if (!output) {
          const message = stderr.trim() ? `No diff output. Stderr: ${stderr.trim()}` : "No changes detected.";
          return {
            content: [{ type: "text" as const, text: message }],
          };
        }

        return {
          content: [{ type: "text" as const, text: output }],
        };
      } catch (err: any) {
        return {
          content: [
            {
              type: "text" as const,
              text: `Error executing git diff: ${err?.message ?? String(err)}`,
            },
          ],
        };
      }
    },
  };
}

export interface RoleToolOptions {
  read?: any;
  grep?: any;
  find?: any;
  ls?: any;
  write?: any;
  edit?: any;
  bash?: any;
}

/**
 * Factory function that constructs the strictly authorized tool set for a given role.
 */
export function createRoleTools(
  role: AgentRole,
  workspaceDir: string,
  options?: RoleToolOptions
): any[] {
  let tools: any[];

  switch (role) {
    case "planner":
      tools = [
        createReadTool(workspaceDir, options?.read),
        createGrepTool(workspaceDir, options?.grep),
        createFindTool(workspaceDir, options?.find),
        createLsTool(workspaceDir, options?.ls),
      ];
      break;

    case "coder":
      tools = [
        createReadTool(workspaceDir, options?.read),
        createWriteTool(workspaceDir, options?.write),
        createEditTool(workspaceDir, options?.edit),
        createBashTool(workspaceDir, options?.bash),
        createGitDiffTool(workspaceDir),
      ];
      break;

    case "reviewer":
      tools = [
        createReadTool(workspaceDir, options?.read),
        createGrepTool(workspaceDir, options?.grep),
        createFindTool(workspaceDir, options?.find),
        createLsTool(workspaceDir, options?.ls),
        createGitDiffTool(workspaceDir),
      ];
      break;

    default: {
      const _exhaustive: never = role;
      throw new LeastPrivilegeViolationError(`Unhandled role: ${_exhaustive}`);
    }
  }

  // Enforce least-privilege contract before returning
  assertRoleToolPrivileges(
    role,
    tools.map((t) => t.name)
  );

  return tools;
}
