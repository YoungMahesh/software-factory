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

Implemented the Pre-flight Guard and Issue Tracker Parser across both TypeScript (`sandbox/factory/preflight.ts`) and Python (`factory/preflight.py`):
1. **Pre-flight Guard**: `validatePreflight` / `validate_preflight` and `assertPreflight` / `assert_preflight` validate the presence of `.scratch/<feature>/spec.md`, `CONTEXT.md` (at repo root or under domain directories), and issue tracking configuration (`docs/agents/issue-tracker.md` or `## Agent skills` in `AGENTS.md` / `CLAUDE.md`), throwing a descriptive `PreflightError` with actionable remediation messages if any are missing.
2. **Issue Tracker Parser**: `parseTicket` / `parse_ticket` parses markdown ticket headers (`Status:`, `Blocked by:`) handling bold formatting and multiple blockers. `parseTickets` / `parse_tickets` discovers all tickets in `.scratch/<feature>/issues/` sorted numerically.
3. **Frontier Resolution**: `getFrontierTickets` / `get_frontier_tickets` identifies open, unblocked tickets on the frontier in numerical order where all dependencies in `Blocked by:` are resolved.
4. **Test Suite & Typechecking**: 100% test coverage with automated unit and smoke tests in Node.js (`sandbox/factory/preflight.test.ts`, tested via `node --test --experimental-strip-types`) and Python (`tests/test_preflight.py`, tested via `pytest`), fully typed and verified clean with `tsc` and `mypy`.
