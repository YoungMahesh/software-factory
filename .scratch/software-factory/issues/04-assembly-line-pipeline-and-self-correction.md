# 04: Assembly Line Pipeline and Self-Correction Loop

**What to build:** The in-sandbox assembly line pipeline coordinator and autonomous batch runner that stitches all stages into an automated lifecycle with self-correction. It executes the Pre-flight Guard on the cloned target repository, checks out `factory/<feature>`, parses `.scratch/<feature>/issues/`, and sequentially executes tickets on the frontier. For each ticket, it runs the Planner to produce `plan.md`, directs the Coder to implement changes and reproduction tests, runs the Deterministic Verifier, and invokes the Reviewer. If tests fail or the review rejects the diff, it loops diagnostics back to the Coder for up to 2 retries. On persistent failure, it marks the ticket `Status: ready-for-human`, commits failure diagnostics, and halts the batch immediately (fail-fast). On success, it commits and pushes to `origin factory/<feature>` immediately, updates the ticket inline to `Status: resolved`, and proceeds to the next unblocked ticket on the frontier.

**Blocked by:** 03: OpenCode Go Provider and Pi Agent Harness

**Status:** resolved

- [x] Orchestrates sequential pipeline stages: Pre-flight ➔ Planner ➔ Coder ➔ Verifier ➔ Reviewer
- [x] Enforces a maximum 2-retry self-correction loop when test runs fail or reviews reject changes
- [x] Captures error diagnostics and feeds them back into the Coder during retry loops
- [x] Sets ticket to `Status: ready-for-human` with error details appended when retries are exhausted, halting the batch immediately
- [x] Commits verified changes to the shared feature branch (`factory/<feature>`) and immediately pushes to `origin factory/<feature>` per resolved ticket
- [x] Updates the local markdown ticket inline with `Status: resolved`, commit SHA, branch name, and quality gate audit summaries
- [x] Supports both targeted single-ticket execution (`--issue <id>`) and autonomous batch mode iterating over all unblocked frontier tickets

## Comments

Implemented the in-sandbox assembly line pipeline coordinator and self-correction loop in TypeScript across four modular seams following TDD per ADR 0027 and ADR 0028:

1. **Inline Ticket Updater (`sandbox/factory/ticket.ts`)**:
   - Updates target repository tickets in `.scratch/<feature>/issues/` inline with `Status: resolved` or `Status: ready-for-human`.
   - Records metadata headers (`Branch: factory/<feature>`, `Commit: <sha>`) and appends Quality Gate audit summaries or failure diagnostics under `## Comments`.
   - Tested in `ticket.test.ts`.

2. **Feature Branch & Git Coordinator (`sandbox/factory/git.ts`)**:
   - `ensureFeatureBranch`: Validates and checks out `factory/<feature>`, tracking `origin/factory/<feature>` if present or creating from current HEAD.
   - `commitAndPushFeatureBranch`: Stages changes, commits with structured conventional messages, and immediately pushes to `origin factory/<feature>`.
   - `commitFailureDiagnostics`: Commits updated tickets marked `ready-for-human` with failure diagnostics to the feature branch.
   - Tested in `git.test.ts`.

3. **Single Ticket Lifecycle & Self-Correction Loop (`sandbox/factory/lifecycle.ts`)**:
   - Executes sequential pipeline stages: Planner ➔ Coder ➔ Deterministic Verifier ➔ Reviewer.
   - Saves generated `plan.md` to `.scratch/<feature>/plan.md` and archives under `.scratch/<feature>/plans/`.
   - Enforces a maximum 2-retry self-correction loop when test runs fail or reviews reject changes.
   - Feeds structured failure diagnostics (verifier output or reviewer issue breakdown) back into the Coder during retries.
   - When retries are exhausted, sets ticket to `Status: ready-for-human`, commits diagnostics, and returns failure.
   - Tested in `lifecycle.test.ts`.

4. **Assembly Line Pipeline Coordinator (`sandbox/factory/pipeline.ts`)**:
   - Stage 0 Pre-flight Guard validates `.scratch/<feature>/spec.md`, `CONTEXT.md`/`GLOSSARY.md`, and issue tracking configuration before stage execution begins.
   - Supports targeted single-ticket mode (`--issue <id>`) and autonomous batch mode sequentially iterating over unblocked frontier tickets.
   - Halts immediately (fail-fast) on ticket failure.
   - Provides CLI dispatcher handling `--workspace`, `--feature`, `--issue`, `--model`, and `--no-push`.
   - Tested in `pipeline.test.ts`.

5. **Test Coverage & Type Safety**:
   - 79 passing tests across all unit, integration, and smoke test suites (`pnpm --prefix sandbox/factory test`).
   - 100% clean typecheck (`pnpm --prefix sandbox/factory typecheck` via `tsc --noEmit`).

