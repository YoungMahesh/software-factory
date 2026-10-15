# 06: Decompose StudioView.tsx

**What to build:**
Decompose `factory/ui/frontend/src/views/StudioView.tsx` (1,052 physical lines) into focused sub-components and hooks under `factory/ui/frontend/src/views/studio/`:
- Create `factory/ui/frontend/src/views/studio/`:
  - `StudioHeader.tsx`: Repo dropdown, new app trigger, branch status pill, PR status banner, and merge trigger.
  - `StudioChatPane.tsx`: Scrollable turn message list, Grilling Assistant questions, reasoning deltas, tool invocation chips, and delivery gate cards.
  - `StudioPreviewPane.tsx`: Live preview frame wrapper, branch synchronization indicator, and viewport controls.
  - `StudioModals.tsx`: Consolidated modal coordinator (NewAppModal, DisconnectedModal, RollbackConfirmModal).
- Refactor `StudioView.tsx`:
  - Compose `StudioHeader`, `StudioPreviewPane`, `StudioChatPane`, and `StudioModals`.
  - Target size for `StudioView.tsx`: $\le 300$ physical lines.
- Invariant: Each newly created component must be $\le 500$ physical lines (`wc -l`).
- Verification: Run `pnpm test` in `factory/ui/frontend` (`StudioView.test.tsx`, `App.test.tsx`) to ensure all UI tests and interactions pass without test modifications.

**Blocked by:** 05-decompose-factory-ui-app

**Status:** resolved
**Triage:** ready-for-agent

- [x] Create `factory/ui/frontend/src/views/studio/` directory and implement sub-components (`StudioHeader.tsx`, `StudioChatPane.tsx`, `StudioPreviewPane.tsx`, `StudioModals.tsx`).
- [x] Refactor `StudioView.tsx` to orchestrate these modular components.
- [x] Ensure all sub-components and `StudioView.tsx` are $\le 500$ physical lines.
- [x] Run `pnpm test` in `factory/ui/frontend` and confirm all tests pass.
