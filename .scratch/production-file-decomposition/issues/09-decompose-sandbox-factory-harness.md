# 09: Decompose sandbox/factory/harness.ts

**What to build:**
Decompose `sandbox/factory/harness.ts` (708 physical lines) into a cohesive package `sandbox/factory/harness/`:
- Create `sandbox/factory/harness/`:
  - `types.ts`: Interface definitions (`ImplementationPlan`, `ReviewVerdict`, `ReviewIssue`), errors (`PlanParseError`, `ReviewParseError`).
  - `prompts.ts`: System prompts and role configurations for `PLANNER`, `CODER`, and `REVIEWER` agents.
  - `parser.ts`: Markdown plan and review verdict output parsers, json extraction, and validation logic.
  - `runner.ts`: Multi-stage assembly line agent executor, tool privilege validation, and self-correction loop management.
  - `index.ts`: Re-export public interfaces and classes so callers importing from `./harness.ts` remain 100% compatible.
- Invariant: Each internal file must be $\le 500$ physical lines (`wc -l`).
- Verification: Run `pnpm test` in `sandbox/factory` (`harness.test.ts`, `pipeline.test.ts`) to ensure all harness tests pass without modification.

**Blocked by:** 08-decompose-issue-drawer

**Status:** resolved
**Triage:** ready-for-agent

- [x] Create `sandbox/factory/harness/` directory and internal sub-modules (`types.ts`, `prompts.ts`, `parser.ts`, `runner.ts`).
- [x] Move logic into respective sub-modules ensuring each is $\le 500$ physical lines.
- [x] Provide `index.ts` re-exporting all symbols and update `sandbox/factory/harness.ts` to proxy re-exports.
- [x] Verify `pnpm test` passes in `sandbox/factory`.
