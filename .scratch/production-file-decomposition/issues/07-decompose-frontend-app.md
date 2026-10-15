# 07: Decompose factory/ui/frontend/src/App.tsx

**What to build:**
Decompose `factory/ui/frontend/src/App.tsx` (853 physical lines) into cohesive hooks and layout components:
- Extract `factory/ui/frontend/src/hooks/useAppTelemetry.ts`:
  - SSE telemetry stream subscription (`useJobStream`), event folding (`foldTelemetryEvents`), and live log/thinking event state tracking.
- Extract `factory/ui/frontend/src/components/AppNavigation.tsx`:
  - Tab navigation bar (`studio` vs `console`), repository switcher, and global theme/status indicators.
- Refactor `App.tsx`:
  - Retain top-level router providers (`QueryClientProvider`, `StudioProvider`), drawer toggles, and clean tab routing.
  - Target size for `App.tsx`: $\le 300$ physical lines.
- Invariant: Each newly extracted file must be $\le 500$ physical lines (`wc -l`).
- Verification: Run `pnpm test` in `factory/ui/frontend` (`App.test.tsx`) to ensure existing tests pass without modification.

**Blocked by:** 06-decompose-studio-view

**Status:** resolved
**Triage:** ready-for-agent

- [x] Create `useAppTelemetry.ts` and migrate SSE event stream orchestration.
- [x] Create `AppNavigation.tsx` and migrate header tab navigation controls.
- [x] Refactor `App.tsx` to orchestrate navigation and providers cleanly.
- [x] Confirm all touched files are $\le 500$ physical lines.
- [x] Verify `pnpm test` passes in `factory/ui/frontend`.
