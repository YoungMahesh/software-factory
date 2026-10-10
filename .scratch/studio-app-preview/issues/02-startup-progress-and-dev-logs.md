# 02: Real-time Startup Observability & Dev Server Logs Drawer

**What to build:** Provide complete real-time visibility during sandbox boot, dependency installation, and Vite dev server compilation. When a preview is launched, the right panel displays a 3-stage progress stepper (`Provisioning sandbox` → `Installing dependencies` → `Starting dev server`) driven by an SSE log stream. An inline collapsible "Dev Server Logs" terminal drawer streams the raw output from `pnpm install` and Vite dev server. If startup fails or dependencies fail to install, the error is caught, the terminal drawer expands with full error diagnostics, and a "Retry" button is displayed. Switching between repositories in the dropdown seamlessly updates the active logs and preview view without UI flicker or losing running state.

**Blocked by:** 01: Core Dedicated Preview Sandbox & Live Iframe Workspace

**Status:** resolved

- [x] SSE endpoint (`GET /api/studio/repos/{repo}/preview/stream`) streams real-time stdout/stderr lines and stage transition events.
- [x] Right-panel workspace displays a visual 3-stage progress stepper while the preview is provisioning.
- [x] Collapsible "Dev Server Logs" terminal drawer displays live streaming output from repository clone, dependency installation, and Vite dev server startup.
- [x] Preview toolbar includes a toggle button to show or hide the dev server terminal logs drawer at any time.
- [x] If container boot, `pnpm install`, or dev server compilation fails, the logs drawer auto-expands with exact failure output and a "Retry" button.
- [x] Switching between repositories in the Factory Studio dropdown dynamically updates the preview pane to reflect that repository's active preview and logs without interrupting other running sandboxes.
- [x] Tests verify SSE streaming event contract, progress stepper state transitions, log drawer expanding/collapsing, and retry on failure.

## Answer

Implemented real-time startup observability, 3-stage progress stepper, dev server logs drawer, and dynamic repository switching:
1. **Real-time SSE Stream & Stage Tracking**: Implemented `GET /api/studio/repos/{repo}/preview/stream` in `factory/ui/app.py` streaming initial state snapshot (`init`) followed by real-time stdout/stderr chunks (`log`), monotonic stage updates (`stage`), and status changes (`status`). Extended `PreviewRegistry` and `PreviewState` in `factory/ui/registry.py` with `buffer_and_extract_lines`, regex pattern detection for clone, `pnpm install`, keep-alive daemon, and Vite dev server compilation failures (`[vite:esbuild]`, `SyntaxError:`, `Failed to compile`).
2. **3-Stage Progress Stepper**: Created `PreviewProgressStepper.tsx` visually guiding users through `Provisioning sandbox` → `Installing dependencies` → `Starting dev server` → `SERVING` with active, completed, and failure states driven by live SSE events.
3. **Collapsible Dev Server Logs Drawer**: Integrated a collapsible terminal drawer in `LivePreview.tsx` embedding `TerminalLogViewer` for raw streaming logs. Added toolbar toggle button (`data-testid="toggle-dev-logs-btn"`), automatic drawer expansion upon failure, and prominent "Retry" controls in the drawer and center failure state.
4. **Dynamic Repository Switching**: Integrated live `EventSource` preview streaming across repository selection changes in `App.tsx` and `StudioView.tsx`, seamlessly updating active logs, stages, and iframe preview without losing running sandboxes or causing UI flicker.
5. **Standards Compliance & Verification**: Aligned terminology strictly with `CONTEXT.md` ("Modal Standard Sandbox"), removed duplicated controls, and verified full test suite: 197 passing Python unit and integration tests (`tests/test_preview.py`, `tests/test_ui.py`), 45 passing Vitest frontend component tests, and zero type errors (`tsc` and `mypy factory`).

