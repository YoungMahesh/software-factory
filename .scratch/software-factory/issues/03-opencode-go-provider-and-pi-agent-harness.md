# 03: OpenCode Go Provider and Pi Agent Harness

**What to build:** An in-sandbox agent harness that integrates the Pi Agent framework with the OpenCode Go subscription API and implements the specialized, least-privilege roles for the assembly line. It configures model connectivity for `DeepSeek V4.1 Flash` (default) and `MiMo-V2.6-Flash` using the decrypted OpenCode API key. It defines the Planner Agent (strictly read-only tools to inspect the repository and draft implementation plans), the Coder Agent (read, write, edit, and bash tools to implement changes and reproduction tests), and the Reviewer Agent (read-only tools to inspect diffs and evaluate code standards).

**Blocked by:** 01: Pre-flight Guard and Issue Tracker Parser, 02: Deterministic Verifier and Test Execution Harness

**Status:** resolved

- [x] Configures OpenCode Go inference using `OPENCODE_GO_API_KEY` for `DeepSeek V4.1 Flash` and `MiMo-V2.6-Flash`
- [x] Implements the read-only Planner Agent with file viewing, search, and directory navigation tools
- [x] Ensures the Planner Agent generates structured implementation plans specifying affected files and test commands
- [x] Implements the Coder Agent with file editing, diffing, and shell execution capabilities
- [x] Implements the read-only Reviewer Agent to inspect git diffs, tickets, and plans and emit structured review verdicts
- [x] Enforces least-privilege tool restrictions per agent role

## Comments

Implemented the OpenCode Go Provider and Pi Agent Harness in TypeScript (`sandbox/factory/provider.ts`, `sandbox/factory/tools.ts`, `sandbox/factory/harness.ts`) per ADR 0025 and ADR 0026 following TDD across 4 confirmed public seams:
1. **OpenCode Go Provider & Model Resolver (`provider.ts`)**: Resolves the OpenCode API key with precedence (`apiKey` option ➔ `OPENCODE_GO_API_KEY` env ➔ decrypted `~/.config/opencode/opencode.env` ➔ fallback `OPENCODE_API_KEY`). Configures `@earendil-works/pi-ai` provider `opencode-go` restricted strictly to supported models: `DeepSeek V4.1 Flash` (`deepseek-v4.1-flash`, default flagship model) and `MiMo-V2.6-Flash` (`mimo-v2.6-flash`). Rejects unsupported models with actionable `ProviderConfigError`.
2. **Least-Privilege Tool Boundaries (`tools.ts`)**: Defines role-specific tool suites:
   - **Planner Agent**: strictly read-only tools (`read`, `grep`, `find`, `ls`). Throws `LeastPrivilegeViolationError` if any mutating tool (`write`, `edit`, `bash`) is provided.
   - **Coder Agent**: full editing, diffing, and execution capabilities (`read`, `write`, `edit`, `bash`, `diff`).
   - **Reviewer Agent**: strictly read-only tools (`read`, `grep`, `find`, `ls`, `diff`). Throws `LeastPrivilegeViolationError` if any mutating tool (`write`, `edit`, `bash`) is provided.
   - Dedicated `createGitDiffTool` inspects working tree changes, staged commits, and custom revisions without granting arbitrary bash shell access to read-only roles.
3. **Structured Plan & Verdict Parsers (`harness.ts`)**:
   - `parseImplementationPlan`: extracts structured `ImplementationPlan` from JSON blocks or markdown sections, enforcing that both `affectedFiles` and `testCommands` are non-empty. Throws `PlanParseError` on invalid plans.
   - `parseReviewVerdict`: extracts structured `ReviewVerdict` (`approved` or `rejected`), assessing spec compliance, standards compliance, structured issues, and actionable remediation notes. Throws `ReviewParseError` if verdict is ambiguous or missing.
4. **Assembly Line Agent Runners (`harness.ts`)**: Implements `runPlannerAgent`, `runCoderAgent`, and `runReviewerAgent` using `@earendil-works/pi-agent-core` with least-privilege enforcement, prompt engineering tailored per stage, and self-correction diagnostics feedback for the Coder stage.
5. **Full Test Coverage & Type Safety**: 62 unit, smoke, and integration tests passing cleanly across `provider.test.ts`, `tools.test.ts`, `parsers.test.ts`, `harness.test.ts`, `verifier.test.ts`, `preflight.test.ts`, and full integration suites. Verified 100% clean with `tsc --noEmit`.
