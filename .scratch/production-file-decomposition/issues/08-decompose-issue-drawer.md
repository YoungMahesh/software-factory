# 08: Decompose factory/ui/frontend/src/components/IssueDrawer.tsx

**What to build:**
Decompose `factory/ui/frontend/src/components/IssueDrawer.tsx` (715 physical lines) into focused sub-components under `factory/ui/frontend/src/components/issue-drawer/`:
- Create `factory/ui/frontend/src/components/issue-drawer/`:
  - `IssueCard.tsx`: Individual issue item rendering, triage labels, "Grill & Align" action, and "Instant Dispatch" action.
  - `MilestoneGroup.tsx`: Accordion group for milestone-clustered issues with batch execution controls (`onRunMilestone`).
  - `IssueFilterBar.tsx`: Search input, open/closed/milestone tab filter pills, and refresh button.
  - `index.ts`: Re-export `IssueDrawer` component and types.
- Refactor `IssueDrawer.tsx`:
  - Compose `IssueFilterBar`, `MilestoneGroup`, and `IssueCard` within the slide-over drawer frame.
  - Target size for `IssueDrawer.tsx`: $\le 300$ physical lines.
- Invariant: Each component must be $\le 500$ physical lines (`wc -l`).
- Verification: Run `pnpm test` in `factory/ui/frontend` to ensure drawer rendering and event dispatches pass unmodified.

**Blocked by:** 07-decompose-frontend-app

**Status:** ready-for-agent
**Triage:** ready-for-agent

- [ ] Create `factory/ui/frontend/src/components/issue-drawer/` directory and internal components.
- [ ] Migrate `IssueCard`, `MilestoneGroup`, and `IssueFilterBar` logic.
- [ ] Refactor `IssueDrawer.tsx` to orchestrate sub-components.
- [ ] Confirm all touched files are $\le 500$ physical lines.
- [ ] Verify `pnpm test` passes in `factory/ui/frontend`.
