# 03: OpenCode Go Provider and Pi Agent Harness

**What to build:** An in-sandbox agent harness that integrates the Pi Agent framework with the OpenCode Go subscription API and implements the specialized, least-privilege roles for the assembly line. It configures model connectivity for `DeepSeek V4.1 Flash` (default) and `MiMo-V2.6-Flash` using the decrypted OpenCode API key. It defines the Planner Agent (strictly read-only tools to inspect the repository and draft implementation plans), the Coder Agent (read, write, edit, and bash tools to implement changes and reproduction tests), and the Reviewer Agent (read-only tools to inspect diffs and evaluate code standards).

**Blocked by:** 01: Pre-flight Guard and Issue Tracker Parser, 02: Deterministic Verifier and Test Execution Harness

**Status:** ready-for-agent

- [ ] Configures OpenCode Go inference using `OPENCODE_GO_API_KEY` for `DeepSeek V4.1 Flash` and `MiMo-V2.6-Flash`
- [ ] Implements the read-only Planner Agent with file viewing, search, and directory navigation tools
- [ ] Ensures the Planner Agent generates structured implementation plans specifying affected files and test commands
- [ ] Implements the Coder Agent with file editing, diffing, and shell execution capabilities
- [ ] Implements the read-only Reviewer Agent to inspect git diffs, tickets, and plans and emit structured review verdicts
- [ ] Enforces least-privilege tool restrictions per agent role
