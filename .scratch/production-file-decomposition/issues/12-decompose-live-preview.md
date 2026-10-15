# 12: Decompose factory/ui/frontend/src/components/LivePreview.tsx

**What to build:**
Decompose `factory/ui/frontend/src/components/LivePreview.tsx` (660 physical lines) into focused sub-components under `factory/ui/frontend/src/components/live-preview/`:
- Create `factory/ui/frontend/src/components/live-preview/`:
  - `LivePreviewToolbar.tsx`: Viewport mode toggles (desktop/tablet/mobile), reload button, external link, branch dropdown, and trunk sync button.
  - `LivePreviewFrame.tsx`: Iframe viewport container with responsive dimension styling based on selected ViewportMode.
  - `LivePreviewOverlay.tsx`: Status overlays for stopped, launching, error, and disconnected preview states.
  - `index.ts`: Re-export `LivePreview` component.
- Refactor `LivePreview.tsx`:
  - Compose `LivePreviewToolbar`, `LivePreviewFrame`, and `LivePreviewOverlay`.
  - Target size for `LivePreview.tsx`: $\le 250$ physical lines.
- Invariant: Each component must be $\le 500$ physical lines (`wc -l`).
- Verification: Run `pnpm test` in `factory/ui/frontend` to ensure preview interactions and toolbar buttons pass unmodified.

**Blocked by:** 11-decompose-sandbox-main

**Status:** ready-for-agent
**Triage:** ready-for-agent

- [ ] Create `factory/ui/frontend/src/components/live-preview/` directory and internal components.
- [ ] Migrate toolbar, frame, and overlay logic into sub-components.
- [ ] Refactor `LivePreview.tsx` to orchestrate sub-components cleanly.
- [ ] Confirm all touched files are $\le 500$ physical lines.
- [ ] Verify `pnpm test` passes in `factory/ui/frontend`.
