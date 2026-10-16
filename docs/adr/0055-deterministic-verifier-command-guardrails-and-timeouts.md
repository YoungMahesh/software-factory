# Deterministic Verifier Command Guardrails and Timeouts

**Status**: Accepted (Amends [ADR 0023](0023-software-factory-assembly-line-architecture.md) and [ADR 0038](0038-unified-studio-sandbox-for-live-preview-and-agent-execution.md))

To prevent the Software Factory assembly line from stalling indefinitely when autonomous agents propose interactive or persistent daemon processes as verification checks, we decided to enforce strict command filtering and bounded execution timeouts in the Deterministic Verifier.

## Considered Options

- **Unbounded Execution with Agent Prompts Only**: Relying solely on the Planner Agent's system prompt to avoid specifying dev or daemon commands in implementation plans. Rejected because autonomous LLM planners occasionally hallucinate manual verification commands (such as `pnpm dev` or `vite dev`) into `testCommands`, causing the verifier subprocess to hang indefinitely without feedback.
- **Global Stage Timeout Only**: Terminating the entire verifier stage if it exceeds a global deadline (e.g. 10 minutes). Rejected because it fails slowly and masks runaway daemon processes as generic stage timeouts, wasting container time and delaying agent recovery.
- **Defense-in-Depth (Dev Server Filtering, Plan Parsing Validation, and 60-Second Command Timeouts)**: 
  1. Filtering long-running dev servers (`pnpm dev`, `vite`, `npm start`, etc.) out of verification commands across both Studio and batch modes.
  2. Rejecting plans in `parseImplementationPlan` whose only test commands are daemon processes.
  3. Updating `PLANNER_SYSTEM_PROMPT` to explicitly forbid interactive and dev server commands.
  4. Enforcing a default 60-second execution timeout per command in `runCommand` and `verifyWorkspace`.
  Accepted because it stops daemon commands before execution, falls back to discovered test suites when available, and guarantees bounded runtimes for all verification suites.

## Consequences

- The canonical term **Deterministic Verifier** in `CONTEXT.md` is updated to reflect non-interactive execution and bounded timeouts.
- [`sandbox/factory/verifier.ts`](file:///root/software-factory/sandbox/factory/verifier.ts) exports `isDevServerCommand()` and strips dev server invocations prior to command execution.
- [`sandbox/factory/verifier.ts`](file:///root/software-factory/sandbox/factory/verifier.ts) and [`sandbox/factory/lifecycle.ts`](file:///root/software-factory/sandbox/factory/lifecycle.ts) enforce a default per-command timeout of 60,000ms.
- [`sandbox/factory/harness/prompts.ts`](file:///root/software-factory/sandbox/factory/harness/prompts.ts) explicitly instructs the Planner Agent to only emit automated, terminating test suites.
- [`sandbox/factory/harness/parser.ts`](file:///root/software-factory/sandbox/factory/harness/parser.ts) strips dev commands from parsed plans and validates that non-daemon test commands remain.
