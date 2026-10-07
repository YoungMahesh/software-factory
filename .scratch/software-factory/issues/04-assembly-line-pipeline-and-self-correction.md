# 04: Assembly Line Pipeline and Self-Correction Loop

**What to build:** The assembly line pipeline coordinator running inside the sandbox that stitches all stages into an automated lifecycle with self-correction. It executes the Pre-flight Guard, runs the Planner to produce the plan, directs the Coder to implement changes and reproduction tests, runs the Deterministic Verifier against test suites, and invokes the Reviewer. If tests fail or the review rejects the diff, it loops failure diagnostics back to the Coder for up to 2 retry attempts. On persistent failure, it marks the ticket `Status: ready-for-human`. On success, it commits and pushes to the shared feature branch (`factory/<feature>`) and updates the ticket to `Status: resolved` with a full audit trail.

**Blocked by:** 03: OpenCode Go Provider and Pi Agent Harness

**Status:** ready-for-agent

- [ ] Orchestrates the sequential pipeline stages: Pre-flight ➔ Planner ➔ Coder ➔ Verifier ➔ Reviewer
- [ ] Enforces a maximum 2-retry self-correction loop when test runs fail or reviews reject changes
- [ ] Captures error diagnostics and feeds them back into the Coder during retry loops
- [ ] Sets ticket to `Status: ready-for-human` with error details appended when retries are exhausted
- [ ] Commits verified changes to the shared feature branch (`factory/<feature>`) and pushes to the remote git origin
- [ ] Updates the local markdown ticket inline with `Status: resolved`, commit SHA, branch name, and quality gate audit summaries
