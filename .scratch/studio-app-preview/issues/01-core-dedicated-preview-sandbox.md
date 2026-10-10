# 01: Core Dedicated Preview Sandbox & Live Iframe Workspace

**What to build:** When a developer selects a repository in Factory Studio, allow them to immediately launch and interact with the application in the right panel. Selecting an app presents a "Preview App" button in the top control bar and a "Launch Live Preview" CTA in the empty preview panel. Clicking either provisions an ephemeral Dedicated Preview Sandbox on Modal with port 3000 exposed via a Modal Application Tunnel, bypassing agent stages. The sandbox checks out the active feature branch (or `main`), runs `pnpm dev`, resolves the unique HTTPS tunnel URL (`https://<sandbox-id>-3000.modal.host`), and embeds the live app inside the right-panel iframe. The developer can switch viewports (desktop, tablet, mobile), refresh the frame, open it in an external tab, see the active branch badge, and click a red "Stop" button to cleanly terminate the sandbox.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] "Preview App" button appears in the Factory Studio top control bar next to the repository selector.
- [x] Prominent "Launch Live Preview" primary CTA button appears in the right panel when no preview is running for the selected app.
- [x] Backend provisions an ephemeral Modal Standard Sandbox configured with `encrypted_ports=[3000]`, `ENABLE_CLOUDFLARE=0`, and a 30-minute idle timeout (`idle_timeout=1800`), without invoking Planner/Coder/Verifier/Reviewer agents.
- [x] Sandbox checks out the active Feature Branch (`factory/<feature>`) if an active milestone/issue exists; otherwise checks out `main`.
- [x] Spawner captures and returns the unique Modal Application Tunnel URL (`sandbox.tunnels()[3000].url`) as the preview URL.
- [x] In-memory preview registry manages active preview state per repository (`repo -> PreviewState`).
- [x] REST API endpoints for preview lifecycle (`POST /api/studio/repos/{repo}/preview`, `GET /api/studio/repos/{repo}/preview`, `DELETE /api/studio/repos/{repo}/preview`) are implemented and authenticated.
- [x] Right panel embeds the live application inside an `<iframe>` pointing to the Modal tunnel URL upon readiness.
- [x] Preview toolbar displays active branch badge (`main` or `factory/<feature>`) and a red "Stop" button that terminates the sandbox.
- [x] End-to-end HTTP integration tests and frontend component tests verify launch, iframe embedding, and termination.

## Answer

Implemented the complete Dedicated Preview Sandbox and Live Iframe Workspace:
1. **Preview Spawner & Sandbox Configuration**: Implemented `create_preview_sandbox` / `spawn_preview_sandbox` in `factory/spawner.py` configuring Modal Standard Sandboxes with `encrypted_ports=[3000]`, `idle_timeout=1800` (30 minutes), `ENABLE_CLOUDFLARE="0"`, bypassing the multi-agent assembly line pipeline via container entrypoint flag `--preview-only` and capturing the HTTPS tunnel URL (`sandbox.tunnels()[3000].url`).
2. **Branch Resolution & In-Memory Preview Registry**: Added `resolve_active_preview_branch` and `PreviewRegistry` in `factory/ui/registry.py` managing thread-safe `repo -> PreviewState` mappings, automatically selecting `factory/<feature>` when active milestones or scratch items exist, or defaulting to `main`.
3. **REST API Endpoints**: Implemented and authenticated `POST /api/studio/repos/{repo}/preview`, `GET /api/studio/repos/{repo}/preview`, and `DELETE /api/studio/repos/{repo}/preview` in `factory/ui/app.py`.
4. **Studio & Live Preview Frontend**: Added "Preview App" control bar button in `StudioView.tsx`, "Launch Live Preview" primary CTA button and active branch badge in `LivePreview.tsx`, red "Stop" sandbox termination button, and live Modal tunnel URL iframe embedding in `LivePreview.tsx` and `App.tsx`.
5. **Testing**: Verified end-to-end with unit and integration tests in `tests/test_preview.py` and `tests/test_ui.py` (190 passing tests), and Vitest component specs in `LivePreview.test.tsx` and `StudioView.test.tsx` (34 passing tests).
