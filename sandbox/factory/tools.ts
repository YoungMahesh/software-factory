import fs from "node:fs";
import path from "node:path";
import os from "node:os";
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
  planner: ["read", "grep", "find", "ls", "web_search", "docs_search"],
  coder: ["read", "write", "edit", "bash", "diff", "web_search", "docs_search"],
  reviewer: ["read", "grep", "find", "ls", "diff"],
};

export const FORBIDDEN_MUTATING_TOOLS = ["write", "edit", "bash"] as const;

export interface ApiKeyResolutionOptions {
  apiKey?: string;
  envPath?: string;
  configFiles?: string[];
}

function textResult(text: string) {
  return { content: [{ type: "text" as const, text }] };
}

function combineSignal(signal?: AbortSignal, ms = 10000): AbortSignal {
  const timeout = AbortSignal.timeout(ms);
  return signal ? (AbortSignal as any).any([signal, timeout]) : timeout;
}

function parseEnvFileForKey(filePath: string, keyName: string): string | undefined {
  if (!fs.existsSync(filePath)) return undefined;
  try {
    for (const line of fs.readFileSync(filePath, "utf-8").split("\n")) {
      const match = line.trim().match(/^(?:export\s+)?([A-Za-z0-9_]+)=(.*)$/);
      if (match && match[1] === keyName) return match[2].trim().replace(/^['"]|['"]$/g, "");
    }
  } catch {}
  return undefined;
}

function resolveApiKey(
  keyName: "EXA_API_KEY" | "CONTEXT7_API_KEY",
  options?: ApiKeyResolutionOptions
): string | undefined {
  if (options?.apiKey && options.apiKey.trim().length > 0) {
    return options.apiKey.trim();
  }

  if (
    process.env[keyName] &&
    process.env[keyName]!.trim().length > 0 &&
    process.env[keyName] !== "undefined"
  ) {
    return process.env[keyName]!.trim();
  }

  const defaultConfigFiles = [
    path.join(os.homedir(), ".config", "opencode", "opencode.env"),
    "/root/.factory.env",
  ];
  const candidateFiles = options?.envPath
    ? [options.envPath]
    : options?.configFiles ?? defaultConfigFiles;

  for (const file of candidateFiles) {
    const val = parseEnvFileForKey(file, keyName);
    if (val && val.length > 0) {
      return val;
    }
  }

  return undefined;
}

/**
 * Resolves Exa API key prioritizing explicit option, ambient EXA_API_KEY env var,
 * and sandbox config files (~/.config/opencode/opencode.env, /root/.factory.env).
 */
export function resolveExaApiKey(options?: ApiKeyResolutionOptions): string | undefined {
  return resolveApiKey("EXA_API_KEY", options);
}

/**
 * Resolves Context7 API key prioritizing explicit option, ambient CONTEXT7_API_KEY env var,
 * and sandbox config files (~/.config/opencode/opencode.env, /root/.factory.env).
 */
export function resolveContext7ApiKey(options?: ApiKeyResolutionOptions): string | undefined {
  return resolveApiKey("CONTEXT7_API_KEY", options);
}

export class LeastPrivilegeViolationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "LeastPrivilegeViolationError";
  }
}

export interface ExaToolOptions extends ApiKeyResolutionOptions {
  fetchFn?: typeof fetch;
}

/**
 * Creates the read-only web_search tool powered by Exa AI Search API.
 */
export function createExaWebSearchTool(options?: ExaToolOptions) {
  return {
    name: "web_search",
    description:
      "Search the web for modern documentation, library guides, release notes, and error solutions using Exa AI Search.",
    parameters: Type.Object({
      query: Type.String({ description: "Search query string" }),
      numResults: Type.Optional(
        Type.Integer({ description: "Number of search results to return (1-5, default 3)" })
      ),
    }),
    execute: async (
      _toolCallId: string,
      params: { query: string; numResults?: number },
      signal?: AbortSignal
    ) => {
      const apiKey = resolveExaApiKey(options);
      if (!apiKey) {
        return textResult(
          "Error: Exa API key not found. Ensure EXA_API_KEY is configured in environment or ~/.config/opencode/opencode.env"
        );
      }

      const trimmedQuery = params.query?.trim();
      if (!trimmedQuery) return textResult("Error: Search query cannot be empty.");

      const numResults = Math.min(Math.max(params.numResults ?? 3, 1), 5);

      try {
        const fetchImpl = options?.fetchFn ?? fetch;
        const response = await fetchImpl("https://api.exa.ai/search", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "x-api-key": apiKey,
            Authorization: `Bearer ${apiKey}`,
          },
          body: JSON.stringify({
            query: trimmedQuery,
            numResults,
            contents: { text: { maxCharacters: 1000 } },
          }),
          signal: combineSignal(signal, 10000),
        });

        if (!response.ok) {
          const errorBody = await response.text().catch(() => "");
          return textResult(
            `Exa search API error (HTTP ${response.status}): ${errorBody || response.statusText}`
          );
        }

        const data: any = await response.json();
        const results = Array.isArray(data?.results) ? data.results : [];
        if (results.length === 0) {
          return textResult(`No web search results found for query: "${trimmedQuery}".`);
        }

        const formatted = results
          .map((result: any, idx: number) => {
            const title = result.title?.trim() || `Result #${idx + 1}`;
            const url = result.url?.trim() || "";
            return [
              url ? `### [${title}](${url})` : `### ${title}`,
              url ? `**URL:** ${url}` : null,
              result.author?.trim() ? `**Author:** ${result.author.trim()}` : null,
              result.text?.trim() || null,
            ]
              .filter(Boolean)
              .join("\n\n");
          })
          .join("\n\n---\n\n");

        return textResult(formatted);
      } catch (err: any) {
        return textResult(`Error executing web search: ${err?.message ?? String(err)}`);
      }
    },
  };
}

export interface Context7ToolOptions extends ApiKeyResolutionOptions {
  fetchFn?: typeof fetch;
}

/**
 * Creates the read-only docs_search tool powered by Context7 API.
 */
export function createContext7DocsTool(options?: Context7ToolOptions) {
  return {
    name: "docs_search",
    description:
      "Search official library documentation, component code snippets, and CLI commands using Context7.",
    parameters: Type.Object({
      query: Type.String({ description: "Technical documentation query, task, or question" }),
      library: Type.Optional(
        Type.String({ description: "Target library name (e.g. Next.js, react, tailwindcss)" })
      ),
      language: Type.Optional(
        Type.String({
          description: "Preferred programming language (e.g. TypeScript, JavaScript, Python)",
        })
      ),
    }),
    execute: async (
      _toolCallId: string,
      params: { query: string; library?: string; language?: string },
      signal?: AbortSignal
    ) => {
      const apiKey = resolveContext7ApiKey(options);
      if (!apiKey) {
        return textResult(
          "Error: Context7 API key not found. Ensure CONTEXT7_API_KEY is configured in environment or ~/.config/opencode/opencode.env"
        );
      }

      const trimmedQuery = params.query?.trim();
      if (!trimmedQuery) return textResult("Error: Search query cannot be empty.");

      try {
        const fetchImpl = options?.fetchFn ?? fetch;
        const url = new URL("https://context7.com/api/v3/search");
        url.searchParams.set("query", trimmedQuery);
        url.searchParams.set("type", "json");
        if (params.library?.trim()) url.searchParams.set("library", params.library.trim());
        if (params.language?.trim()) url.searchParams.set("language", params.language.trim());

        const response = await fetchImpl(url.toString(), {
          method: "GET",
          headers: {
            Authorization: `Bearer ${apiKey}`,
            CONTEXT7_API_KEY: apiKey,
          },
          signal: combineSignal(signal, 10000),
        });

        if (!response.ok) {
          const errorBody = await response.text().catch(() => "");
          return textResult(
            `Context7 docs API error (HTTP ${response.status}): ${errorBody || response.statusText}`
          );
        }

        const rawText = await response.text();
        let data: any;
        try {
          data = JSON.parse(rawText);
        } catch {
          return textResult(rawText);
        }

        const blocks: string[] = [];
        if (Array.isArray(data?.codeSnippets)) {
          for (const snippet of data.codeSnippets) {
            const title =
              snippet.codeTitle?.trim() || snippet.pageTitle?.trim() || "Documentation Snippet";
            const parts: string[] = [`### ${title}`];
            if (snippet.codeDescription?.trim()) parts.push(snippet.codeDescription.trim());
            const src = snippet.codeId?.trim() || snippet.pageTitle?.trim() || snippet.libraryId?.trim();
            if (src) parts.push(`**Source:** ${src}`);

            if (Array.isArray(snippet.codeList) && snippet.codeList.length > 0) {
              for (const codeItem of snippet.codeList) {
                const lang = codeItem.language || snippet.codeLanguage || "";
                parts.push(`\`\`\`${lang}\n${codeItem.code}\n\`\`\``);
              }
            } else if (snippet.code?.trim()) {
              parts.push(`\`\`\`${snippet.codeLanguage || ""}\n${snippet.code}\n\`\`\``);
            }
            blocks.push(parts.join("\n\n"));
          }
        }

        if (Array.isArray(data?.infoSnippets)) {
          for (const info of data.infoSnippets) {
            const label = info.breadcrumb?.trim() || info.pageId?.trim() || "Reference";
            if (info.content?.trim()) blocks.push(`**${label}:** ${info.content.trim()}`);
          }
        }

        if (blocks.length === 0) {
          return textResult(`No documentation results found for query: "${trimmedQuery}".`);
        }

        return textResult(blocks.join("\n\n---\n\n"));
      } catch (err: any) {
        return textResult(`Error executing docs search: ${err?.message ?? String(err)}`);
      }
    },
  };
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
    description:
      "Inspect git diff of working tree changes, staged changes, or against a commit/branch in the target repository.",
    parameters: Type.Object({
      cached: Type.Optional(
        Type.Boolean({ description: "View staged changes only (--cached / --staged)" })
      ),
      commit: Type.Optional(
        Type.String({
          description: "Specific commit or revision to diff against (e.g. HEAD, origin/main)",
        })
      ),
      path: Type.Optional(Type.String({ description: "Specific file or directory path to diff" })),
    }),
    execute: async (
      _toolCallId: string,
      params: { cached?: boolean; commit?: string; path?: string },
      _signal?: AbortSignal
    ) => {
      const args = ["diff"];
      if (params.cached) args.push("--staged");
      if (params.commit) {
        if (params.commit.startsWith("-")) {
          return textResult("Error: Commit revision cannot start with a dash.");
        }
        args.push(params.commit);
      }
      if (params.path) args.push("--", params.path);

      try {
        const { stdout, stderr } = await pExecFile("git", args, {
          cwd: workspaceDir,
          maxBuffer: 10 * 1024 * 1024,
        });

        const output = stdout.trim();
        if (!output) {
          const message = stderr.trim()
            ? `No diff output. Stderr: ${stderr.trim()}`
            : "No changes detected.";
          return textResult(message);
        }

        return textResult(output);
      } catch (err: any) {
        return textResult(`Error executing git diff: ${err?.message ?? String(err)}`);
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
  web_search?: ExaToolOptions;
  docs_search?: Context7ToolOptions;
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
        createExaWebSearchTool(options?.web_search),
        createContext7DocsTool(options?.docs_search),
      ];
      break;

    case "coder":
      tools = [
        createReadTool(workspaceDir, options?.read),
        createWriteTool(workspaceDir, options?.write),
        createEditTool(workspaceDir, options?.edit),
        createBashTool(workspaceDir, options?.bash),
        createGitDiffTool(workspaceDir),
        createExaWebSearchTool(options?.web_search),
        createContext7DocsTool(options?.docs_search),
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
