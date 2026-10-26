# 03: In-Sandbox Headless Visual QA and Console Crash Detection

**What to build:**
An automated visual quality gate and crash detection stage running inside the sandbox against the local development server on port 3000 during the Assembly Line Pipeline. Using pre-baked headless Google Chrome and Playwright, the verifier checks that the application mounts successfully, verifies the Clean Canvas Invariant, catches unhandled browser runtime errors or console exceptions, captures full-page desktop and mobile viewport screenshots as artifacts, and feeds browser stack traces into the Self-Correction Loop on failure.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] In-sandbox verification stage connects to the local development server via Playwright using pre-baked headless Google Chrome with container sandbox flags.
- [ ] Clean Canvas Invariant verification asserts that the application root DOM container has positive bounding dimensions and non-empty rendered markup within a bounded timeout.
- [ ] Browser runtime exception trap collects all uncaught page errors and error-level console logs, failing the verification stage if fatal errors occur.
- [ ] Fatal browser errors format the console output and stack traces into structured error payloads for consumption by the Coder Agent's Self-Correction Loop.
- [ ] Successful runs capture desktop (1280x800) and mobile (390x844) full-page viewport screenshots saved to the pipeline artifacts directory.
- [ ] Emits structured visual QA telemetry markers over the standard output stream for ingestion by the studio event demuxer.
- [ ] Automated tests verify Clean Canvas assertions, crash detection on intentional browser runtime errors, screenshot generation, and execution timeout bounds.
