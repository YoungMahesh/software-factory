# 02: Repository Codebase Grounding and Source Context Ingestion

**What to build:** Implement autonomous codebase fact-finding in the Grilling Assistant before formulating questions. When a developer submits a prompt in Factory Studio, the assistant discovers the repository layout (routes and components) from GitHub on the active feature branch (`factory/<milestone>`) or `main`, identifies candidate files matching keywords from the developer's prompt (e.g. matching `Footer.tsx` when the prompt mentions social links), and injects the file tree and component source code into the LLM system prompt. This ensures grilling questions are grounded in existing code rather than hallucinating new routes.

**Blocked by:** 01 (OpenCode Go Endpoint Configuration and Transparent Error Turns)

**Status:** ready-for-agent

- [ ] Grilling service checks for active milestone branches (`factory/<milestone>`) on GitHub, falling back to `main`.
- [ ] Grilling service retrieves the recursive git tree via GitHub API and extracts route and component file paths.
- [ ] File paths are scored against keywords extracted from the prompt to locate relevant candidate source files.
- [ ] Raw source code for the top matching candidate files (up to three files, max 25KB total) is retrieved from GitHub.
- [ ] Repository tree summary and candidate source code bodies are injected into the LLM system prompt under structured sections.
- [ ] Prompts modifying or removing elements in existing components generate questions focused on those components rather than proposing new route files.
