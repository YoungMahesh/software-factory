# 03: Live Preview Toolbar Interactive Selector UI and Concurrency Lock

**What to build:**
Upgrade the active branch badge in the Live Preview toolbar into an interactive dropdown selector with strict concurrency locking during active agent assembly line jobs. Developers can click the branch pill to inspect all candidate branches for the repository, select a branch to switch the live preview in place, observe real-time switching feedback with a loading spinner, and enjoy automatic preview refreshes. When an Assembly Line Pipeline job is active (`RUNNING` or `QUEUED`), the branch selector is strictly disabled with a lock icon and tooltip to prevent concurrent git conflicts while agents are generating code.

**Blocked by:** 02: In-Container In-Place Git Switching and Diff-Aware Dependency Resolution

**Status:** resolved

- [x] `#preview-branch-badge` in `LivePreview.tsx` is transformed into an interactive dropdown menu with `GitBranch` icon, branch label, and `ChevronDown`.
- [x] Dropdown lists available branches with a checkmark indicator next to the currently active branch.
- [x] Selecting a branch invokes branch switching, displays a loading spinner inside the badge, and disables interaction during the transition.
- [x] Concurrency guard: Selector is strictly disabled with a lock icon and explanatory tooltip when an Assembly Line Pipeline job is `RUNNING` or `QUEUED`.
- [x] `StudioView.tsx` integrates TanStack Query to fetch branches for the active repository, invalidating cache on repository switch, job completion, and drawer interactions.
- [x] Switching branch triggers automatic preview iframe refresh upon completion.
- [x] Dropdown supports keyboard navigation and click-away closing.
- [x] Automated Vitest component and integration tests verify dropdown rendering, branch selection, loading states, concurrency locking, and query invalidation.

## Answer

Delivered the interactive Live Preview branch selector and concurrency lock:
1. **Interactive Dropdown Badge (`LivePreview.tsx`)**:
   - Replaced static branch pill with interactive dropdown button (`#preview-branch-badge`) displaying `GitBranch` icon, branch label, and `ChevronDown` (or loading spinner during branch switch).
   - Rendered dropdown menu listing all candidate branches (`availableBranches` / `branches`), with a checkmark indicator on the currently active branch.
   - Preserved backward-compatible fallback to static badge when no switch handler is provided or branch list is empty.
   - Built full keyboard navigation (`ArrowDown`, `ArrowUp`, `Enter`, `Escape`) and outside-click dismiss handling.
2. **Strict Concurrency Locking**:
   - Strictly locked and disabled the dropdown whenever an Assembly Line Pipeline job is active (`isJobActive` / `isConcurrencyLocked` when job is `RUNNING` or `QUEUED`).
   - Replaced chevron with `Lock` icon and applied canonical tooltip: `"Branch switching is disabled while an Assembly Line Pipeline job is active"`.
3. **TanStack Query State & Invalidation (`useStudioQueries.ts`, `StudioView.tsx`, `App.tsx`)**:
   - Created `useRepoBranchesQuery(repo)` and `useUpdatePreviewBranchMutation()`.
   - Wired cache invalidation on repository selection, pipeline job completion (`SUCCESS`), and issue drawer interactions.
   - Triggered preview iframe reloads upon successful switch; preserved current preview without reload on error and displayed non-destructive `branch-switch-error-toast` pointing to Dev Server Logs drawer.
4. **Verification**:
   - 100% test coverage across unit, component, view, and app levels: 149 tests passing across 22 test files with zero TypeScript typecheck errors.

