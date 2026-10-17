# 0063: Web Search and Documentation Tools for Assembly Line Agents

**Status**: Accepted

To enable autonomous assembly line agents in Factory Studio to retrieve up-to-date documentation, component code snippets, CLI installation commands, and technical web resources without hallucinations or pipeline aborts, we decided to introduce dedicated, read-only `web_search` (powered by Exa) and `docs_search` (powered by Context7) tools for the Planner Agent and Coder Agent in the Pi Agent Harness.

## Context

When autonomous assembly line agents build frontend applications inside isolated Modal sandboxes, they operate in rapidly evolving technology ecosystems (such as TanStack Start, React 19, Tailwind CSS v4, and modern UI component libraries). The LLMs powering these agents frequently suffer from knowledge cutoffs, hallucinated package APIs, outdated configuration conventions, or obsolete CLI commands.

Previously, agents were confined entirely to local repository file tools (`read`, `grep`, `find`, `ls`) and shell commands. Without live access to official documentation and web resources:
1. The **Planner Agent** could not verify modern package architectures or library version compatibility when planning implementation steps.
2. The **Coder Agent** struggled to diagnose modern framework errors or look up accurate component props and code examples, leading to broken builds, failed verifier passes, and unnecessary self-correction retries.
3. Reviewer Agent audit boundaries needed to be strictly preserved to prevent external search drift from influencing code audit verdicts.

## Decision

1. **Two Distinct Tool Abstractions**:
   - **Exa Web Search Tool (`web_search`)**: Powered by the Exa AI Search API (`https://api.exa.ai/search`) using `EXA_API_KEY` from OpenCode Credentials. Designed for open-web exploration, framework release notes, library compatibility checks, and troubleshooting modern compiler/bundler errors. Requests 3 results by default (configurable 1–5) with a maximum of 1,000 characters per text extract.
   - **Context7 Documentation Tool (`docs_search`)**: Powered by the Context7 API (`https://context7.com/api/v3/search`) using `CONTEXT7_API_KEY` from OpenCode Credentials. Designed for targeted lookup of official library documentation, CLI installation commands, and component code snippets with optional `library` and `language` filters.

2. **Least-Privilege Role Authorization**:
   - Update `ROLE_ALLOWED_TOOLS` and `createRoleTools()` to authorize `web_search` and `docs_search` for both `planner` and `coder` agent roles.
   - The **Planner Agent** remains strictly read-only: mutating tools (`write`, `edit`, `bash`) remain strictly forbidden (`FORBIDDEN_MUTATING_TOOLS`).
   - The **Reviewer Agent** remains strictly restricted to local repository inspection (`read`, `grep`, `find`, `ls`, `diff`) without external search tools, protecting audit boundaries.

3. **Three-Tier Credential Resolution**:
   - Implement `resolveExaApiKey()` and `resolveContext7ApiKey()` with a prioritized fallback chain:
     1. Explicit option override (e.g. `options.apiKey`), facilitating isolated unit testing without ambient state.
     2. Ambient environment variables (`EXA_API_KEY`, `CONTEXT7_API_KEY`).
     3. Sandbox filesystem configuration (`~/.config/opencode/opencode.env` or `/root/.factory.env`).
   - Return `undefined` when credentials cannot be resolved, allowing tools to report clear diagnostic messages rather than crashing.

4. **Resilient Error Surface & Token Budgeting**:
   - Bounded 10-second timeout using `AbortSignal.timeout(10000)` combined with any caller abort signals.
   - Tools validate queries and return structured error messages as text content upon missing credentials, empty queries, HTTP non-200 responses, or network timeouts.
   - Exceptions are never thrown to the agent runner, preventing unexpected pipeline terminations.
   - Structured markdown formatting: `web_search` formats titles, URLs, authors, and text snippets; `docs_search` parses code snippets into syntax-highlighted code fences with titles, descriptions, and source references.

5. **Externalized System Prompt Guidance**:
   - Update `sandbox/factory/harness/prompts/planner_system.md` and `coder_system.md` with explicit guidelines on when to use `docs_search` (library syntax and snippets) and `web_search` (ecosystem search and error debugging), emphasizing that local repository file inspection remains the primary source of truth for existing code.

## Consequences

- **Domain Model**: Canonical glossary terms for **Exa Web Search Tool** and **Context7 Documentation Tool** are recorded in [`CONTEXT.md`](../../CONTEXT.md).
- **Reduced Hallucinations**: Agents can look up official component APIs and modern framework patterns directly during both planning and coding phases.
- **Audit Purity**: The Reviewer Agent remains strictly local-only, ensuring that PR quality verdicts are grounded entirely in repo diffs and accepted ADRs.
- **Universal File Line Budget**: `sandbox/factory/tools.ts` and `sandbox/factory/tools.test.ts` comply with the <= 500 lines budget.
