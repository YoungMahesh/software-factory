# 01: Core Dedicated Preview Sandbox & Live Iframe Workspace

**What to build:** When a developer selects a repository in Factory Studio, allow them to immediately launch and interact with the application in the right panel. Selecting an app presents a "Preview App" button in the top control bar and a "Launch Live Preview" CTA in the empty preview panel. Clicking either provisions an ephemeral Dedicated Preview Sandbox on Modal with port 3000 exposed via a Modal Application Tunnel, bypassing agent stages. The sandbox checks out the active feature branch (or `main`), runs `pnpm dev`, resolves the unique HTTPS tunnel URL (`https://<sandbox-id>-3000.modal.host`), and embeds the live app inside the right-panel iframe. The developer can switch viewports (desktop, tablet, mobile), refresh the frame, open it in an external tab, see the active branch badge, and click a red "Stop" button to cleanly terminate the sandbox.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] "Preview App" button appears in the Factory Studio top control bar next to the repository selector.
- [ ] Prominent "Launch Live Preview" primary CTA button appears in the right panel when no preview is running for the selected app.
- [ ] Backend provisions an ephemeral Modal Standard Sandbox configured with `encrypted_ports=[3000]`, `ENABLE_CLOUDFLARE=0`, and a 30-minute idle timeout (`idle_timeout=1800`), without invoking Planner/Coder/Verifier/Reviewer agents.
- [ ] Sandbox checks out the active Feature Branch (`factory/<feature>`) if an active milestone/issue exists; otherwise checks out `main`.
- [ ] Spawner captures and returns the unique Modal Application Tunnel URL (`sandbox.tunnels()[3000].url`) as the preview URL.
- [ ] In-memory preview registry manages active preview state per repository (`repo -> PreviewState`).
- [ ] REST API endpoints for preview lifecycle (`POST /api/studio/repos/{repo}/preview`, `GET /api/studio/repos/{repo}/preview`, `DELETE /api/studio/repos/{repo}/preview`) are implemented and authenticated.
- [ ] Right panel embeds the live application inside an `<iframe>` pointing to the Modal tunnel URL upon readiness.
- [ ] Preview toolbar displays active branch badge (`main` or `factory/<feature>`) and a red "Stop" button that terminates the sandbox.
- [ ] End-to-end HTTP integration tests and frontend component tests verify launch, iframe embedding, and termination.
