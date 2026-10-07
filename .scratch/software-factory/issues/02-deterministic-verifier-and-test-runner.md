# 02: Deterministic Verifier and Test Execution Harness

**What to build:** A non-agentic verification module that objectively executes automated test and lint suites against a repository workspace. It accepts a target directory and command strings (discovered from repository config or proposed in plans), executes them in child processes, streams outputs, and captures process exit codes. It determines whether a test run passed or failed purely on exit status, guaranteeing that test results cannot be hallucinated by language models.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Executes specified test and lint commands within the target repository workspace
- [ ] Streams standard output and standard error during execution
- [ ] Captures process exit codes to evaluate pass (status 0) vs. fail (non-zero) deterministically
- [ ] Returns structured verification logs with captured output and status codes
- [ ] Handles process timeouts and command execution failures gracefully
