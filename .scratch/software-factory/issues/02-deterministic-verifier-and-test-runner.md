# 02: Deterministic Verifier and Test Execution Harness

**What to build:** A non-agentic verification module that objectively executes automated test and lint suites against a repository workspace. It accepts a target directory and command strings (discovered from repository config or proposed in plans), executes them in child processes, streams outputs, and captures process exit codes. It determines whether a test run passed or failed purely on exit status, guaranteeing that test results cannot be hallucinated by language models.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] Executes specified test and lint commands within the target repository workspace
- [x] Streams standard output and standard error during execution
- [x] Captures process exit codes to evaluate pass (status 0) vs. fail (non-zero) deterministically
- [x] Returns structured verification logs with captured output and status codes
- [x] Handles process timeouts and command execution failures gracefully

## Comments

Implemented the Deterministic Verifier and Test Execution Harness in TypeScript (`sandbox/factory/verifier.ts`) following TDD at confirmed public seams:
1. **Core Process Execution (`runCommand`)**: Executes commands in child processes via subshell in the target repository workspace, captures combined interleaved output, separate stdout, and separate stderr. Evaluates pass purely on deterministic process exit code (`code === 0 && signal === null`).
2. **Real-time Output Streaming**: Streams chunks in real time as they arrive via `onStream?: (chunk, stream) => void` handler and optional `streamToProcess: boolean` for live terminal feedback.
3. **Timeout & Failure Resilience**: Enforces configurable execution timeouts (`timeoutMs`), terminating child process trees and process groups (`SIGTERM` followed by `SIGKILL` escalation). Catches and isolates process spawn errors and directory access failures without unhandled rejections.
4. **Structured Verification Harness (`verifyWorkspace`)**: Executes lists of test and lint commands in the target workspace with `failFast` support (defaulting to halting on first failure). Emits structured `VerificationResult` containing command list metrics and a markdown audit summary table with failure diagnostics for upstream assembly line stages and ticket comments.
5. **Config-Driven Command Discovery (`discoverCommands`)**: Intelligently discovers test, lint, and typecheck commands across Node (`package.json` with npm, pnpm, yarn, bun package manager awareness), Python (`pyproject.toml`, `pytest.ini`, ruff), Rust (`Cargo.toml`), and Go (`go.mod`) when commands are not explicitly specified.
6. **Full Test Coverage & Type Safety**: 17 unit, smoke, and integration tests in `sandbox/factory/verifier.test.ts` verifying all requirements, pass/fail exit code determinism, signal handling, streaming, timeouts, failure details, and workspace discovery. Fully verified clean with `tsc --noEmit`.
