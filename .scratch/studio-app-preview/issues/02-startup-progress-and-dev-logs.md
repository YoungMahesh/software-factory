# 02: Real-time Startup Observability & Dev Server Logs Drawer

**What to build:** Provide complete real-time visibility during sandbox boot, dependency installation, and Vite dev server compilation. When a preview is launched, the right panel displays a 3-stage progress stepper (`Provisioning sandbox` → `Installing dependencies` → `Starting dev server`) driven by an SSE log stream. An inline collapsible "Dev Server Logs" terminal drawer streams the raw output from `pnpm install` and Vite dev server. If startup fails or dependencies fail to install, the error is caught, the terminal drawer expands with full error diagnostics, and a "Retry" button is displayed. Switching between repositories in the dropdown seamlessly updates the active logs and preview view without UI flicker or losing running state.

**Blocked by:** 01: Core Dedicated Preview Sandbox & Live Iframe Workspace

**Status:** ready-for-agent

- [ ] SSE endpoint (`GET /api/studio/repos/{repo}/preview/stream`) streams real-time stdout/stderr lines and stage transition events.
- [ ] Right-panel workspace displays a visual 3-stage progress stepper while the preview is provisioning.
- [ ] Collapsible "Dev Server Logs" terminal drawer displays live streaming output from repository clone, dependency installation, and Vite dev server startup.
- [ ] Preview toolbar includes a toggle button to show or hide the dev server terminal logs drawer at any time.
- [ ] If container boot, `pnpm install`, or dev server compilation fails, the logs drawer auto-expands with exact failure output and a "Retry" button.
- [ ] Switching between repositories in the Factory Studio dropdown dynamically updates the preview pane to reflect that repository's active preview and logs without interrupting other running sandboxes.
- [ ] Tests verify SSE streaming event contract, progress stepper state transitions, log drawer expanding/collapsing, and retry on failure.
