# 04: Assembly Line Pipeline and Self-Correction Loop

**What to build:** The in-sandbox assembly line pipeline coordinator and autonomous batch runner that stitches all stages into an automated lifecycle with self-correction. It executes the Pre-flight Guard on the cloned target repository, checks out `factory/<feature>`, parses `.scratch/<feature>/issues/`, and sequentially executes tickets on the frontier. For each ticket, it runs the Planner to produce `plan.md`, directs the Coder to implement changes and reproduction tests, runs the Deterministic Verifier, and invokes the Reviewer. If tests fail or the review rejects the diff, it loops diagnostics back to the Coder for up to 2 retries. On persistent failure, it marks the ticket `Status: ready-for-human`, commits failure diagnostics, and halts the batch immediately (fail-fast). On success, it commits and pushes to `origin factory/<feature>` immediately, updates the ticket inline to `Status: resolved`, and proceeds to the next unblocked ticket on the frontier.

**Blocked by:** 03: OpenCode Go Provider and Pi Agent Harness

**Status:** ready-for-agent

- [ ] Orchestrates sequential pipeline stages: Pre-flight ➔ Planner ➔ Coder ➔ Verifier ➔ Reviewer
- [ ] Enforces a maximum 2-retry self-correction loop when test runs fail or reviews reject changes
- [ ] Captures error diagnostics and feeds them back into the Coder during retry loops
- [ ] Sets ticket to `Status: ready-for-human` with error details appended when retries are exhausted, halting the batch immediately
- [ ] Commits verified changes to the shared feature branch (`factory/<feature>`) and immediately pushes to `origin factory/<feature>` per resolved ticket
- [ ] Updates the local markdown ticket inline with `Status: resolved`, commit SHA, branch name, and quality gate audit summaries
- [ ] Supports both targeted single-ticket execution (`--issue <id>`) and autonomous batch mode iterating over all unblocked frontier tickets
