# 05: Self-Correction Visual States & Failure Cards

**What to build:** Prominent visual diagnostics for failed commands and explicit milestone tracking for self-correction feedback loops. When a command fails with a non-zero exit code or assertion failure, the command card automatically auto-expands with a red error badge, highlighting the failing error output. When the ticket lifecycle initiates a self-correction retry attempt (up to 2 retries), a prominent visual milestone divider is injected into the timeline indicating the new attempt and summarizing the failure reason that the Coder Agent is addressing.

**Blocked by:** 03: Command Execution Timeline & Windowed Output

**Status:** ready-for-agent

- [ ] In-sandbox `sandbox/factory/lifecycle.ts` emits an `attempt_start` telemetry event at each iteration of the self-correction loop, reporting the attempt number (e.g. `attempt: 2, maxRetries: 2`) and diagnostics reason (test failure or reviewer rejection).
- [ ] Host `JobRegistry` detects and forwards attempt milestone events over the SSE stream to connected clients.
- [ ] In the Factory Testing Console UI (`factory/ui/templates/index.html`), any command exiting with a non-zero status code automatically expands its output container and displays a red status badge (`Exit code 1`) with stderr lines highlighted.
- [ ] Attempt transitions render a prominent visual divider card on the timeline (e.g., `🔄 Self-Correction Loop: Attempt 2/3 (Fixing failing test suites)`).
- [ ] If the Reviewer Agent rejects a diff, a Reviewer Rejection Card displays the rejection summary and remediation instructions immediately preceding the next Coder attempt.
- [ ] Tests verify that self-correction loop transitions emit attempt events and that failing commands trigger automatic container expansion in the UI.
