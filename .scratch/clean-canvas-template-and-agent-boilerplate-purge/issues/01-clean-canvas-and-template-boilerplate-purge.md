# 01: Clean Canvas Invariant and Template Boilerplate Purge

**What to build:**
Eliminate default template boilerplate residue and enforce the Clean Canvas Invariant across Factory Studio and newly generated applications:
- **Canonical Template Purge (`software-factory-09-test/tanstack-start-template`)**:
  - Replace `src/routes/index.tsx` placeholder banner ("Application Workspace" and "Ready for development. Prompt Factory Studio to build features and components.") with a clean, empty main container canvas (`<main className="page-wrap px-4 py-8 min-h-screen"></main>`).
  - Update `src/components/Header.tsx` brand badge default from "TanStack Start" to "App".
  - Commit and push to `main` on `software-factory-09-test/tanstack-start-template` using organization credentials.
- **Assembly Line Prompts Defense-in-Depth**:
  - Update `sandbox/factory/harness/prompts/planner_system.md` to instruct the Planner Agent to explicitly plan the replacement of starter template boilerplate copy in `src/routes/index.tsx` and header branding in `src/components/Header.tsx`.
  - Update `sandbox/factory/harness/prompts/coder_system.md` to instruct the Coder Agent to replace starter placeholder cards rather than appending components below them, and update header brand text to match the application title.
  - Update `sandbox/factory/harness/prompts/reviewer_system.md` to require `standardsCompliance` to reject pull requests retaining template placeholder copy ("Application Workspace", "Ready for development", etc.) with blocker severity.
- **Factory Studio Ticket Synthesis (`factory/ui/github/_issues.py`)**:
  - Update `synthesize_ticket_content` to automatically include acceptance criteria for replacing default starter template placeholder elements in `src/routes/index.tsx` and updating `src/components/Header.tsx` brand title.
- **Domain Modeling & ADR 0062**:
  - Define `Clean Canvas Invariant` in `CONTEXT.md`.
  - Record `docs/adr/0062-clean-canvas-invariant-and-template-boilerplate-purge.md`.
- **Automated Verification**:
  - Update `tests/test_ui/test_synthesis.py` and test suites to assert ticket synthesis and prompt invariants pass cleanly.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent
**Triage:** ready-for-agent

- [ ] Strip "Application Workspace" and guidance copy from `src/routes/index.tsx` on `software-factory-09-test/tanstack-start-template`, leaving a clean `<main className="page-wrap px-4 py-8 min-h-screen"></main>`.
- [ ] Update `src/components/Header.tsx` on `software-factory-09-test/tanstack-start-template` to use "App" as the neutral header brand baseline.
- [ ] Add Clean Canvas Invariant requirements to `sandbox/factory/harness/prompts/planner_system.md`.
- [ ] Add Clean Canvas replacement instructions to `sandbox/factory/harness/prompts/coder_system.md`.
- [ ] Add blocker-level template boilerplate rejection rules to `sandbox/factory/harness/prompts/reviewer_system.md`.
- [ ] Update `synthesize_ticket_content` in `factory/ui/github/_issues.py` to include template replacement and header branding criteria.
- [ ] Add `Clean Canvas Invariant` to `CONTEXT.md`.
- [ ] Create `docs/adr/0062-clean-canvas-invariant-and-template-boilerplate-purge.md`.
- [ ] Update unit tests in `tests/test_ui/test_synthesis.py` and verify all tests pass.
