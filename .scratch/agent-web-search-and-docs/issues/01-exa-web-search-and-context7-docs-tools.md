# 01: Exa Web Search and Context7 Documentation Tools for Assembly Line Agents

**What to build:** Implement dedicated, read-only `web_search` (powered by Exa) and `docs_search` (powered by Context7) tools for the Planner Agent and Coder Agent in the Pi Agent Harness, enabling autonomous assembly line agents in Factory Studio to retrieve up-to-date documentation, component code snippets, CLI installation commands, and technical web resources without hallucinations.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] Implement `resolveExaApiKey()` and `resolveContext7ApiKey()` in `sandbox/factory/tools.ts` with prioritized resolution across explicit options, ambient environment variables (`EXA_API_KEY`, `CONTEXT7_API_KEY`), and sandbox config files (`~/.config/opencode/opencode.env`, `/root/.factory.env`).
- [x] Implement `createExaWebSearchTool()` exporting the `web_search` tool with query validation, configurable `numResults` (1-5, default 3), max 1,000 characters per text extract, 10-second timeout (`AbortSignal.timeout(10000)`), and clean markdown output formatting with titles, URLs, authors, and text snippets.
- [x] Implement `createContext7DocsTool()` exporting the `docs_search` tool with query, optional library, and optional language parameters, 10-second timeout, and structured markdown output formatting with titles, descriptions, source references, and syntax-highlighted code blocks.
- [x] Update `ROLE_ALLOWED_TOOLS` and `createRoleTools()` to authorize `web_search` and `docs_search` for both `planner` and `coder` agent roles, while keeping `reviewer` strictly local-only (`read`, `grep`, `find`, `ls`, `diff`) and maintaining `FORBIDDEN_MUTATING_TOOLS` for the Planner Agent.
- [x] Ensure `sandbox/factory/tools.ts` complies with the universal file line budget and ratchet (<= 500 lines).
- [x] Update externalized markdown prompt templates `sandbox/factory/harness/prompts/planner_system.md` and `coder_system.md` with targeted guidance on using `docs_search` for library syntax and code examples and `web_search` for modern web guides and error diagnosis.
- [x] Add comprehensive automated unit tests in `sandbox/factory/tools.test.ts` verifying key resolution, argument validation, graceful error responses without unhandled exceptions, mock HTTP API responses, network error handling, and role privilege boundaries. Verify that `pnpm --dir sandbox/factory test` passes with zero regressions.
- [x] Add canonical glossary definitions for **Exa Web Search Tool** and **Context7 Documentation Tool** in `CONTEXT.md`.
- [x] Record Architectural Decision Record `docs/adr/0063-web-search-and-documentation-tools-for-assembly-line-agents.md` documenting context, tool separation rationale, least-privilege role boundaries, and credential resolution.
