# 01: Pre-flight Guard and Issue Tracker Parser

**What to build:** A repository validation and ticket discovery module. When given a target repository workspace, it validates that the repository is configured for agent workflows under the domain standard, checking for the presence of the feature specification, domain context documentation, and local issue tracking setup. If any prerequisite is missing, it aborts with a clear, actionable error. When valid, it parses the local markdown issue files for a feature, resolves blocking dependencies, and identifies the next open, unblocked ticket on the frontier.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] Validates presence of `.scratch/<feature>/spec.md` in the target repository
- [x] Validates presence of `CONTEXT.md` at the repository root or in domain paths
- [x] Validates presence of issue tracking configuration (`docs/agents/issue-tracker.md` or `## Agent skills` in `AGENTS.md`/`CLAUDE.md`)
- [x] Aborts with an actionable error message if any prerequisite is missing
- [x] Parses markdown ticket headers (`Status:`, `Blocked by:`) across `.scratch/<feature>/issues/`
- [x] Identifies open and unblocked tickets on the frontier in numerical order

## Comments

Implemented the Pre-flight Guard and Issue Tracker Parser in TypeScript (`sandbox/factory/preflight.ts`) per ADR 0028:
1. **Pre-flight Guard**: `validatePreflight` and `assertPreflight` validate the presence of `.scratch/<feature>/spec.md`, `CONTEXT.md` (at repo root or under domain directories), and issue tracking configuration (`docs/agents/issue-tracker.md` or `## Agent skills` in `AGENTS.md` / `CLAUDE.md`), throwing a descriptive `PreflightError` with actionable remediation messages if any are missing.
2. **Issue Tracker Parser**: `parseTicket` parses markdown ticket headers (`Status:`, `Blocked by:`) handling bold formatting and multiple blockers. `parseTickets` discovers all tickets in `.scratch/<feature>/issues/` sorted numerically.
3. **Frontier Resolution**: `getFrontierTickets` and `getNextFrontierTicket` identify open, unblocked tickets on the frontier in numerical order where all dependencies in `Blocked by:` are resolved.
4. **Architecture Refinement (ADR 0028)**: Per ADR 0028, target repositories co-locate tickets in version control and discovery occurs strictly inside the sandbox. The redundant host Python parser was retired in favor of the in-sandbox TypeScript engine.
5. **Test Suite & Typechecking**: 100% test coverage with automated unit and smoke tests in Node.js (`sandbox/factory/preflight.test.ts`, tested via `node --test --experimental-strip-types`), fully typed and verified clean with `pnpm --filter ./sandbox/factory typecheck` (`tsc --noEmit`).
