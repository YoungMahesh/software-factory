# 01: Vite React SPA Implementation & Dual-Route Serving (`/v2`)

**What to build:** Build the compiled Vite React Single Page Application (SPA) with complete feature parity for both Factory Studio and Factory Testing Console, served concurrently alongside the legacy dashboard via FastAPI on `/v2`. Developers can build and hot-reload components via a Vite dev proxy on port 5173, compile to `factory/ui/static/dist/`, and interact with real-time telemetry, stage transitions, prompt dispatch, and the live application preview iframe without disrupting the existing template.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] A modern frontend workspace is established under `factory/ui/frontend/` using Vite, React 19, TypeScript, and Tailwind CSS, with standard package scripts (`pnpm dev`, `pnpm build`, `pnpm test`).
- [x] The Vite development server is configured with proxy rules forwarding `/api` and `/api/jobs/{id}/stream` SSE requests to the running FastAPI server on port 3010.
- [x] Building the frontend compiles all static HTML, JS, and CSS bundles into `factory/ui/static/dist/`.
- [x] FastAPI in `factory/ui/app.py` mounts static asset delivery for `factory/ui/static/dist/` and serves the compiled SPA shell at `/v2` with client-side SPA routing fallback.
- [x] The legacy template at `/` continues functioning without disruption or regression.
- [x] The React SPA implements the full Factory Testing Console interface: repository selector, feature/milestone discovery, launch parameters (model, VM sandbox, dev preview toggles), stage steppers, and a virtualized terminal log viewer with autoscroll and copy actions.
- [x] The React SPA implements the full Factory Studio interface: multi-turn chat timeline, prompt composer with intent guard rejection handling, live TanStack Start preview iframe (port 3000) with responsive viewport toggles and reload button, and top navigation view switcher.
- [x] The React SPA renders the complete Agent Event Stream: pulsating thinking accordions with duration badges, command execution cards with windowed output (100 lines + toggle), tool chips, diff preview widgets, and self-correction attempt dividers.
- [x] The React SPA includes the slide-over Agent Activity drawer, opening smoothly from tool chips or header badge and synchronizing real-time telemetry alongside the live preview iframe.
- [x] Automated tests in `tests/test_ui.py` verify that `/v2` and static assets are correctly served with valid content types, and existing tests continue to pass cleanly.
