# Specification: Web Search and Documentation Tools for Assembly Line Agents

## Problem Statement

When the autonomous assembly line agents (Planner Agent and Coder Agent) build frontend web applications inside isolated Modal sandboxes, they operate in rapidly evolving technology ecosystems (such as TanStack Start, React 19, Tailwind CSS v4, and modern UI component libraries). The LLMs powering these agents frequently suffer from knowledge cutoffs, hallucinated package APIs, outdated configuration conventions, or obsolete CLI commands.

Without live access to official documentation and web resources, the Planner Agent cannot verify modern package architectures or library version compatibility when planning implementation steps, and the Coder Agent struggles to diagnose modern framework errors or look up accurate component props and code examples. This leads to broken builds, failed verifier passes, or unnecessary self-correction retries that degrade the autonomous application delivery process in Factory Studio.

## Solution

Equip both the Planner Agent and Coder Agent in the Pi Agent Harness with two dedicated, read-only external search and documentation tools:
1. **Exa Web Search Tool (`web_search`)**: Powered by the Exa AI Search API (`https://api.exa.ai/search`) using `EXA_API_KEY` from OpenCode Credentials, enabling general web search, troubleshooting, and retrieval of real-time web documentation with clean extracted text.
2. **Context7 Documentation Tool (`docs_search`)**: Powered by the Context7 API (`https://context7.com/api/v3/search`) using `CONTEXT7_API_KEY` from OpenCode Credentials, enabling specialized lookup of official library documentation, CLI installation commands, and component code snippets.

Both tools resolve credentials gracefully, enforce execution timeouts, and return diagnostic error messages as tool output text rather than crashing the pipeline on network or credential failures. The Reviewer Agent remains strictly restricted to local repository inspection to protect audit boundaries.

## User Stories

1. As a software factory developer, I want the Coder Agent to search Context7 for component documentation, so that it can write correct component imports, props, and JSX patterns without guessing.
2. As a software factory developer, I want the Coder Agent to search Exa for modern framework error messages, so that it can quickly find solutions to unexpected compiler or bundler failures during implementation.
3. As a software factory developer, I want the Planner Agent to search the web for library compatibility and latest package releases, so that it can declare accurate package dependencies and verification commands in implementation plans.
4. As a software factory developer, I want the Planner Agent to look up documentation for architectural patterns, so that the implementation plan adheres to modern conventions before coding begins.
5. As an autonomous assembly line agent, I want `web_search` to return clean text extracts alongside URLs and titles, so that I can immediately read documentation content without needing a second tool call.
6. As an autonomous assembly line agent, I want `docs_search` to support library and language filters, so that I can retrieve focused code examples for the specific framework and language used in the target project.
7. As a software factory developer, I want the tools to fail gracefully when an API key is missing, so that the agent can continue implementing changes using local codebase tools and bash rather than aborting the pipeline run.
8. As a software factory developer, I want the tools to enforce a 10-second network timeout, so that slow remote queries do not hang the autonomous batch loop or exceed container budgets.
9. As a platform administrator, I want credentials for Exa and Context7 to be decrypted from repository secrets into protected container environment files, so that keys are never committed in plaintext.
10. As a code reviewer, I want the Reviewer Agent to remain strictly local-only without search tools, so that audit verdicts are based entirely on repository code diffs and accepted architectural records.
11. As a Factory Studio user, I want search and documentation tool invocations to emit structured telemetry events, so that I can observe the agent's research actions in the live Studio activity stream.
12. As a software engineer maintaining the factory harness, I want search tools to support mockable fetch functions, so that automated unit tests can run deterministically offline without consuming live API credits.

## Implementation Decisions

- **Two Distinct Tool Abstractions**: Provide `web_search` (Exa) for open-web exploration and `docs_search` (Context7) for targeted library snippets. Distinct tools allow the LLM to select the exact search modality needed without ambiguity.
- **Least-Privilege Tool Authorization**: Update the role authorization policy so that Planner and Coder have access to `web_search` and `docs_search`, while Reviewer remains limited to local inspection tools. Ensure mutating tools (`write`, `edit`, `bash`) remain strictly forbidden for the Planner.
- **Dynamic Content & Token Budgeting**: Configure `web_search` to request up to 3 results by default (configurable up to 5) with a maximum of 1,000 characters per text extract, keeping prompt context consumption low while delivering sufficient syntax context.
- **Code Snippet Formatting**: Configure `docs_search` to parse Context7 code snippets and format them into readable markdown blocks with titles, descriptions, source references, and syntax-highlighted code fences.
- **Three-Tier Credential Resolution**: Both tools resolve API keys via a prioritized lookup:
  1. Explicit option override (enabling isolated unit testing).
  2. Ambient environment variables (`EXA_API_KEY`, `CONTEXT7_API_KEY`).
  3. Sandbox filesystem configuration (`~/.config/opencode/opencode.env` or `/root/.factory.env`).
- **Resilient Error Surface**: When credentials are missing, queries are empty, or remote HTTP endpoints return non-200 responses, the tools return structured error messages as text content. Exceptions are never propagated to the agent harness to avoid crashing autonomous pipeline runs.
- **Externalized System Prompt Guidance**: Update the external system prompt templates for Planner and Coder with concise rules on when to use `docs_search` (library syntax and snippets) and `web_search` (ecosystem search and error debugging), emphasizing that local file inspection tools must still be used for repository files.

## Testing Decisions

- **Good Test Criteria**: Tests must verify public tool contracts and observable behavior (returned markdown text, argument validation, role privilege boundaries, error messages) rather than internal network implementations.
- **Mocked HTTP Transport**: Unit tests inject mock fetch functions to verify parameter formatting, HTTP headers (e.g. `x-api-key` and `Authorization: Bearer`), payload parsing, and error status handling without network dependencies.
- **Credential Fallback Verification**: Tests verify that key resolution correctly prioritizes explicit options, ambient environment variables, and missing key fallbacks.
- **Role Boundary Regression Testing**: Tests assert that `ROLE_ALLOWED_TOOLS` correctly includes the new tools on Planner and Coder, excludes them from Reviewer, and ensures `assertRoleToolPrivileges` rejects unauthorized usage.
- **Prior Art**: The existing tool test suite for role tools and the git diff inspection tool in the TypeScript factory harness provides the canonical pattern for testing tool execution and error handling.

## Out of Scope

- Implementing interactive human confirmation before agent web searches.
- Persistent search query caching or vector indexing across multiple jobs.
- Web scraping of arbitrary JavaScript-rendered client-side sites beyond Exa's content extraction.
- Adding search tools to the Reviewer Agent stage.

## Further Notes

Both `EXA_API_KEY` and `CONTEXT7_API_KEY` are already configured and encrypted in the repository's SOPS environment file and are automatically provisioned into Modal factory sandboxes at container boot time.
